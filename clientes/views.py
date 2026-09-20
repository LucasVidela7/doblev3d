from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from pedidos.detalle_views import _armar_preparacion
from pedidos.miniaturas import asignar_miniatura_resumen
from pedidos.models import Pago, Pedido, Presupuesto

from .gestion import (
    candidatos_fusion,
    clientes_con_resumen,
    preferencias_cliente,
    resumen_desde_anotaciones,
)
from .models import Cliente, ContactoCliente
from .telefonos import buscar_cliente_por_telefono
from .whatsapp import (
    enlace_whatsapp,
    numero_whatsapp,
    resolver_contexto,
    url_contacto,
)


ESTADOS_PEDIDO_ACTIVOS = [
    "PENDIENTE",
    "PREPARANDO",
    "LISTO",
]


def _pedidos_cliente_queryset():
    return (
        Pedido.objects
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
            "pagos",
        )
        .order_by("-fecha", "-id")
    )


def _presupuestos_cliente_queryset():
    return (
        Presupuesto.objects
        .select_related(
            "cliente",
            "pedido_generado",
        )
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
        )
        .order_by("-fecha", "-id")
    )


def _url_con_filtros(request, **cambios):
    parametros = request.GET.copy()
    for clave, valor in cambios.items():
        if valor in (None, ""):
            parametros.pop(clave, None)
        else:
            parametros[clave] = valor

    query = parametros.urlencode()
    return request.path + (f"?{query}" if query else "")


def _fila_pedido(pedido, incluir_preparacion=False):
    cancelado = pedido.estado == "CANCELADO"
    entregado = pedido.estado == "ENTREGADO"
    activo = pedido.estado in ESTADOS_PEDIDO_ACTIVOS

    preparacion = (
        _armar_preparacion(pedido)
        if incluir_preparacion and activo
        else []
    )
    preparacion_total = len(preparacion)
    preparacion_listos = sum(
        1
        for item in preparacion
        if item["listo"]
    )
    preparacion_porcentaje = (
        int(
            round(
                preparacion_listos
                * 100
                / preparacion_total
            )
        )
        if preparacion_total
        else 0
    )

    saldo = (
        Decimal("0")
        if cancelado
        else pedido.saldo_pendiente
    )

    return {
        "pedido": pedido,
        "total": pedido.total,
        "pagado": pedido.total_pagado,
        "saldo": saldo,
        "estado_pago": (
            "CANCELADO"
            if cancelado
            else pedido.estado_pago
        ),
        "estado_pago_display": (
            "Cancelado"
            if cancelado
            else pedido.estado_pago_display
        ),
        "cancelado": cancelado,
        "entregado": entregado,
        "activo": activo,
        "preparacion": preparacion,
        "preparacion_total": preparacion_total,
        "preparacion_listos": preparacion_listos,
        "preparacion_porcentaje": preparacion_porcentaje,
        "faltantes_stock": sum(
            1
            for item in preparacion
            if item.get("estado_operativo")
            == "FALTANTE"
        ),
    }


def _seguimientos_cliente(
    cliente,
    resumen,
    filas_activas,
    presupuestos_pendientes,
):
    items = []
    hoy = timezone.localdate()

    for fila in filas_activas:
        pedido = fila["pedido"]

        if pedido.estado == "LISTO":
            items.append(
                {
                    "prioridad": 1,
                    "tipo": "PEDIDO_LISTO",
                    "titulo": (
                        f"{pedido.codigo} listo para entregar"
                    ),
                    "detalle": (
                        "Avisale al cliente que ya puede "
                        "coordinar la entrega."
                    ),
                    "accion": "AVISAR CLIENTE",
                    "url": url_contacto(
                        cliente,
                        "PEDIDO_LISTO",
                        pedido=pedido,
                    ),
                }
            )

        if fila["saldo"] > 0:
            items.append(
                {
                    "prioridad": 2,
                    "tipo": "SALDO",
                    "titulo": (
                        f"{pedido.codigo} tiene saldo pendiente"
                    ),
                    "detalle": (
                        f"$ {fila['saldo']:,.0f} pendientes."
                    ),
                    "accion": "RECORDAR PAGO",
                    "url": url_contacto(
                        cliente,
                        "SALDO",
                        pedido=pedido,
                    ),
                }
            )

    for presupuesto in presupuestos_pendientes:
        dias = max(
            (hoy - presupuesto.fecha).days,
            0,
        )
        items.append(
            {
                "prioridad": 3,
                "tipo": "PRESUPUESTO",
                "titulo": (
                    f"{presupuesto.codigo} espera definición"
                ),
                "detalle": (
                    f"Presupuesto enviado hace {dias} día(s)."
                ),
                "accion": "CONSULTAR",
                "url": url_contacto(
                    cliente,
                    "PRESUPUESTO",
                    presupuesto=presupuesto,
                ),
            }
        )

    if (
        resumen["sin_actividad_reciente"]
        and not resumen["pedidos_activos_count"]
        and not resumen["presupuestos_pendientes_count"]
    ):
        dias = resumen["dias_sin_actividad"]
        detalle = (
            f"Sin actividad hace {dias} días."
            if dias is not None
            else "Todavía no registra compras."
        )
        items.append(
            {
                "prioridad": 4,
                "tipo": "REACTIVACION",
                "titulo": "Retomar contacto",
                "detalle": detalle,
                "accion": "ESCRIBIR",
                "url": url_contacto(
                    cliente,
                    "REACTIVACION",
                ),
            }
        )

    return sorted(
        items,
        key=lambda item: item["prioridad"],
    )[:8]


def _eventos_recientes(
    cliente,
    pedidos,
    presupuestos,
    contactos,
):
    eventos = []

    for pedido in pedidos:
        eventos.append(
            {
                "fecha": pedido.fecha,
                "tipo": "PEDIDO",
                "titulo": (
                    f"{pedido.codigo} · "
                    f"{pedido.get_estado_display()}"
                ),
                "detalle": f"Total $ {pedido.total:,.0f}",
            }
        )

    pagos = (
        Pago.objects
        .filter(pedido__cliente=cliente)
        .select_related("pedido")
        .order_by("-fecha", "-id")[:5]
    )
    for pago in pagos:
        eventos.append(
            {
                "fecha": pago.fecha.date(),
                "tipo": "PAGO",
                "titulo": (
                    f"Pago en {pago.pedido.codigo}"
                ),
                "detalle": (
                    f"$ {pago.monto:,.0f} · "
                    f"{pago.get_medio_display()}"
                ),
            }
        )

    for presupuesto in presupuestos:
        eventos.append(
            {
                "fecha": presupuesto.fecha,
                "tipo": "PRESUPUESTO",
                "titulo": (
                    f"{presupuesto.codigo} · "
                    f"{presupuesto.get_estado_display()}"
                ),
                "detalle": (
                    f"Total $ {presupuesto.total:,.0f}"
                ),
            }
        )

    for contacto in contactos:
        eventos.append(
            {
                "fecha": contacto.iniciado_en.date(),
                "tipo": "WHATSAPP",
                "titulo": (
                    "WhatsApp abierto · "
                    f"{contacto.get_motivo_display()}"
                ),
                "detalle": (
                    contacto.referencia
                    or "Contacto con cliente"
                ),
            }
        )

    eventos.sort(
        key=lambda evento: evento["fecha"],
        reverse=True,
    )
    return eventos[:10]


def lista_clientes(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()

    clientes = clientes_con_resumen()

    if busqueda:
        clientes = clientes.filter(
            Q(nombre__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
            | Q(email__icontains=busqueda)
        )

    filas_base = [
        resumen_desde_anotaciones(cliente)
        for cliente in clientes
    ]

    metricas = {
        "total": len(filas_base),
        "con_pedidos": sum(
            1
            for fila in filas_base
            if fila["pedidos_activos_count"] > 0
        ),
        "con_saldo": sum(
            1
            for fila in filas_base
            if fila["saldo_pendiente"] > 0
        ),
        "con_presupuestos": sum(
            1
            for fila in filas_base
            if fila["presupuestos_pendientes_count"] > 0
        ),
        "atencion": sum(
            1
            for fila in filas_base
            if fila["necesita_atencion"]
        ),
        "contactar": sum(
            1
            for fila in filas_base
            if fila["para_contactar"]
        ),
        "sin_actividad": sum(
            1
            for fila in filas_base
            if fila["sin_actividad_reciente"]
        ),
        "total_comprado": sum(
            (
                fila["total_comprado"]
                for fila in filas_base
            ),
            Decimal("0"),
        ),
        "saldo_total": sum(
            (
                fila["saldo_pendiente"]
                for fila in filas_base
            ),
            Decimal("0"),
        ),
    }

    filtros = {
        "pedidos": lambda fila: (
            fila["pedidos_activos_count"] > 0
        ),
        "saldo": lambda fila: (
            fila["saldo_pendiente"] > 0
        ),
        "presupuestos": lambda fila: (
            fila["presupuestos_pendientes_count"] > 0
        ),
        "atencion": lambda fila: (
            fila["necesita_atencion"]
        ),
        "contactar": lambda fila: (
            fila["para_contactar"]
        ),
        "sin_actividad": lambda fila: (
            fila["sin_actividad_reciente"]
        ),
    }

    if estado in filtros:
        filas = [
            fila
            for fila in filas_base
            if filtros[estado](fila)
        ]
    else:
        filas = filas_base

    filtro_urls = {
        "todos": _url_con_filtros(
            request,
            estado=None,
        ),
        "pedidos": _url_con_filtros(
            request,
            estado="pedidos",
        ),
        "saldo": _url_con_filtros(
            request,
            estado="saldo",
        ),
        "presupuestos": _url_con_filtros(
            request,
            estado="presupuestos",
        ),
        "atencion": _url_con_filtros(
            request,
            estado="atencion",
        ),
        "contactar": _url_con_filtros(
            request,
            estado="contactar",
        ),
        "sin_actividad": _url_con_filtros(
            request,
            estado="sin_actividad",
        ),
    }

    return render(
        request,
        "clientes/lista_v2.html",
        {
            "filas": filas,
            "busqueda": busqueda,
            "estado_seleccionado": estado,
            "metricas": metricas,
            "filtro_urls": filtro_urls,
        },
    )


def detalle_cliente(request, cliente_id):
    cliente = get_object_or_404(
        clientes_con_resumen(),
        id=cliente_id,
    )

    if request.method == "POST":
        nombre = request.POST.get(
            "nombre",
            "",
        ).strip()
        telefono = request.POST.get(
            "telefono",
            "",
        ).strip()
        email = request.POST.get(
            "email",
            "",
        ).strip()
        observaciones = request.POST.get(
            "observaciones",
            "",
        ).strip()

        if not nombre:
            messages.error(
                request,
                (
                    "El nombre del cliente no puede "
                    "quedar vacío."
                ),
            )
            return redirect(
                f"{request.path}?editar=1"
            )

        existente = buscar_cliente_por_telefono(
            telefono,
            excluir_id=cliente.id,
        )
        if existente:
            messages.error(
                request,
                (
                    "Ese teléfono ya pertenece a "
                    f"{existente.nombre} "
                    f"({existente.codigo})."
                ),
            )
            return redirect(
                f"{request.path}?editar=1"
            )

        cliente.nombre = nombre
        cliente.telefono = telefono
        cliente.email = email
        cliente.observaciones = observaciones
        cliente.save(
            update_fields=[
                "nombre",
                "telefono",
                "email",
                "observaciones",
            ]
        )

        messages.success(
            request,
            "Datos del cliente actualizados.",
        )
        return redirect(
            "clientes:detalle",
            cliente_id=cliente.id,
        )

    resumen = resumen_desde_anotaciones(
        cliente
    )

    pedidos_activos = list(
        _pedidos_cliente_queryset()
        .filter(
            cliente=cliente,
            estado__in=ESTADOS_PEDIDO_ACTIVOS,
        )
    )
    pedidos_recientes = list(
        _pedidos_cliente_queryset()
        .filter(cliente=cliente)[:5]
    )
    presupuestos_pendientes = list(
        _presupuestos_cliente_queryset()
        .filter(
            cliente=cliente,
            estado="PENDIENTE",
        )[:10]
    )
    presupuestos_recientes = list(
        _presupuestos_cliente_queryset()
        .filter(cliente=cliente)[:5]
    )

    asignar_miniatura_resumen(
        pedidos_activos,
        "detalles",
    )
    asignar_miniatura_resumen(
        pedidos_recientes,
        "detalles",
    )
    asignar_miniatura_resumen(
        presupuestos_pendientes,
        "detalles",
    )
    asignar_miniatura_resumen(
        presupuestos_recientes,
        "detalles",
    )

    filas_ahora = [
        _fila_pedido(
            pedido,
            incluir_preparacion=True,
        )
        for pedido in pedidos_activos
    ]
    filas_pedidos = [
        _fila_pedido(
            pedido,
            incluir_preparacion=(
                pedido.estado
                in ESTADOS_PEDIDO_ACTIVOS
            ),
        )
        for pedido in pedidos_recientes
    ]

    contactos_recientes = list(
        cliente.contactos.all()[:5]
    )
    seguimientos = _seguimientos_cliente(
        cliente,
        resumen,
        filas_ahora,
        presupuestos_pendientes,
    )
    preferencias = preferencias_cliente(
        cliente,
        limite=5,
    )
    duplicados = candidatos_fusion(
        cliente,
        limite=10,
    )

    eventos = _eventos_recientes(
        cliente,
        pedidos_recientes,
        presupuestos_recientes,
        contactos_recientes,
    )

    return render(
        request,
        "clientes/detalle_v2.html",
        {
            "cliente": cliente,
            "filas_ahora": filas_ahora,
            "filas_pedidos": filas_pedidos,
            "presupuestos_pendientes": (
                presupuestos_pendientes
            ),
            "presupuestos": (
                presupuestos_recientes
            ),
            "seguimientos": seguimientos,
            "preferencias": preferencias,
            "contactos_recientes": (
                contactos_recientes
            ),
            "duplicados_sugeridos": duplicados,
            "eventos": eventos,
            "whatsapp_url": url_contacto(
                cliente,
                "GENERICO",
            ),
            "hay_mas_pedidos": (
                resumen["cantidad_pedidos"]
                > len(pedidos_recientes)
            ),
            "hay_mas_presupuestos": (
                resumen["cantidad_presupuestos"]
                > len(presupuestos_recientes)
            ),
            "modo_edicion": (
                request.GET.get("editar") == "1"
            ),
            **resumen,
        },
    )


def historial_cliente(request, cliente_id):
    cliente = get_object_or_404(
        Cliente,
        id=cliente_id,
        activo=True,
    )
    tipo = request.GET.get(
        "tipo",
        "pedidos",
    )
    if tipo not in {
        "pedidos",
        "presupuestos",
        "contactos",
    }:
        tipo = "pedidos"

    elementos = []
    pagina = None

    if tipo == "pedidos":
        consulta = (
            _pedidos_cliente_queryset()
            .filter(cliente=cliente)
        )
        pagina = Paginator(
            consulta,
            20,
        ).get_page(
            request.GET.get("page")
        )
        objetos = list(
            pagina.object_list
        )
        asignar_miniatura_resumen(
            objetos,
            "detalles",
        )
        elementos = [
            _fila_pedido(
                pedido,
                incluir_preparacion=False,
            )
            for pedido in objetos
        ]

    elif tipo == "presupuestos":
        consulta = (
            _presupuestos_cliente_queryset()
            .filter(cliente=cliente)
        )
        pagina = Paginator(
            consulta,
            20,
        ).get_page(
            request.GET.get("page")
        )
        elementos = list(
            pagina.object_list
        )
        asignar_miniatura_resumen(
            elementos,
            "detalles",
        )

    else:
        consulta = (
            ContactoCliente.objects
            .filter(cliente=cliente)
            .order_by("-iniciado_en", "-id")
        )
        pagina = Paginator(
            consulta,
            20,
        ).get_page(
            request.GET.get("page")
        )
        elementos = list(
            pagina.object_list
        )

    return render(
        request,
        "clientes/historial.html",
        {
            "cliente": cliente,
            "tipo": tipo,
            "elementos": elementos,
            "pagina": pagina,
        },
    )


def whatsapp_cliente(request, cliente_id):
    cliente = get_object_or_404(
        Cliente,
        id=cliente_id,
        activo=True,
    )
    numero = numero_whatsapp(cliente)
    if not numero:
        messages.error(
            request,
            "El cliente no tiene un teléfono válido.",
        )
        return redirect(
            "clientes:detalle",
            cliente_id=cliente.id,
        )

    contexto = resolver_contexto(
        cliente,
        request.GET.get(
            "motivo",
            "GENERICO",
        ),
        pedido_id=request.GET.get(
            "pedido",
        ),
        presupuesto_id=request.GET.get(
            "presupuesto",
        ),
    )

    ContactoCliente.objects.create(
        cliente=cliente,
        canal="WHATSAPP",
        motivo=contexto["motivo"],
        referencia=contexto["referencia"],
        mensaje=contexto["mensaje"],
    )

    return HttpResponseRedirect(
        enlace_whatsapp(
            numero,
            contexto["mensaje"],
        )
    )


@transaction.atomic
def fusionar_cliente(request, cliente_id):
    if request.method != "POST":
        return redirect(
            "clientes:detalle",
            cliente_id=cliente_id,
        )

    destino = get_object_or_404(
        Cliente,
        id=cliente_id,
        activo=True,
    )
    origen = get_object_or_404(
        Cliente,
        id=request.POST.get("duplicado_id"),
        activo=True,
    )

    if origen.id == destino.id:
        messages.error(
            request,
            "No se puede fusionar un cliente consigo mismo.",
        )
        return redirect(
            "clientes:detalle",
            cliente_id=destino.id,
        )

    Pedido.objects.filter(
        cliente=origen,
    ).update(
        cliente=destino,
    )
    Presupuesto.objects.filter(
        cliente=origen,
    ).update(
        cliente=destino,
    )
    ContactoCliente.objects.filter(
        cliente=origen,
    ).update(
        cliente=destino,
    )

    campos_actualizados = []

    if (
        not destino.telefono
        and origen.telefono
    ):
        destino.telefono = origen.telefono
        campos_actualizados.append("telefono")

    if (
        not destino.email
        and origen.email
    ):
        destino.email = origen.email
        campos_actualizados.append("email")

    if origen.observaciones:
        texto = (
            f"[Fusionado desde {origen.codigo}] "
            f"{origen.observaciones}"
        )
        destino.observaciones = (
            f"{destino.observaciones}\n\n{texto}".strip()
        )
        campos_actualizados.append(
            "observaciones"
        )

    if campos_actualizados:
        destino.save(
            update_fields=list(
                dict.fromkeys(
                    campos_actualizados
                )
            )
        )

    origen.activo = False
    nota = (
        f"Fusionado en {destino.codigo} "
        f"el {timezone.localdate():%d/%m/%Y}."
    )
    origen.observaciones = (
        f"{origen.observaciones}\n\n{nota}".strip()
    )
    origen.save(
        update_fields=[
            "activo",
            "observaciones",
        ]
    )

    messages.success(
        request,
        (
            f"{origen.codigo} se fusionó en "
            f"{destino.codigo}. Pedidos, presupuestos "
            "y contactos quedaron unificados."
        ),
    )
    return redirect(
        "clientes:detalle",
        cliente_id=destino.id,
    )
