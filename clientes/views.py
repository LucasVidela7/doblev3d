from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from pedidos.detalle_views import _armar_preparacion
from pedidos.miniaturas import asignar_miniatura_resumen
from pedidos.models import Pedido, Presupuesto

from .models import Cliente
from .telefonos import buscar_cliente_por_telefono, normalizar_telefono


def _pedidos_cliente_queryset():
    """Historial completo del cliente, con la información necesaria para operar."""
    return (
        Pedido.objects
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
            "pagos",
        )
        .order_by("-id")
    )


def _presupuestos_cliente_queryset():
    return (
        Presupuesto.objects
        .select_related("cliente", "pedido_generado")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
        )
        .order_by("-id")
    )


def _pedido_vigente(pedido):
    return pedido.estado != "CANCELADO"


def _url_con_filtros(request, **cambios):
    parametros = request.GET.copy()
    for clave, valor in cambios.items():
        if valor in (None, ""):
            parametros.pop(clave, None)
        else:
            parametros[clave] = valor

    query = parametros.urlencode()
    return request.path + (f"?{query}" if query else "")


def _whatsapp_url(cliente):
    clave = normalizar_telefono(cliente.telefono)
    if not clave:
        return ""

    numero = f"549{clave}" if len(clave) == 10 else clave
    mensaje = quote(
        f"Hola {cliente.nombre}! Te escribo de Doble V 3D."
    )
    return f"https://wa.me/{numero}?text={mensaje}"


def _resumen_cliente(cliente, pedidos=None, presupuestos=None):
    pedidos = (
        list(pedidos)
        if pedidos is not None
        else list(_pedidos_cliente_queryset().filter(cliente=cliente))
    )
    presupuestos = (
        list(presupuestos)
        if presupuestos is not None
        else list(_presupuestos_cliente_queryset().filter(cliente=cliente))
    )

    pedidos_vigentes = [
        pedido for pedido in pedidos
        if _pedido_vigente(pedido)
    ]
    pedidos_activos = [
        pedido for pedido in pedidos_vigentes
        if pedido.estado not in ["ENTREGADO", "CANCELADO"]
    ]
    pedidos_listos = [
        pedido for pedido in pedidos_activos
        if pedido.estado == "LISTO"
    ]
    presupuestos_pendientes = [
        presupuesto for presupuesto in presupuestos
        if presupuesto.estado == "PENDIENTE"
    ]

    total_comprado = sum(
        (pedido.total for pedido in pedidos_vigentes),
        Decimal("0"),
    )
    total_pagado = sum(
        (pedido.total_pagado for pedido in pedidos_vigentes),
        Decimal("0"),
    )
    saldo_pendiente = sum(
        (pedido.saldo_pendiente for pedido in pedidos_vigentes),
        Decimal("0"),
    )

    hoy = timezone.localdate()
    limite_entrega = hoy + timedelta(days=2)
    entregas_proximas = [
        pedido for pedido in pedidos_activos
        if pedido.fecha_entrega
        and pedido.fecha_entrega <= limite_entrega
    ]

    fechas_actividad = [
        pedido.fecha for pedido in pedidos
        if pedido.fecha
    ] + [
        presupuesto.fecha for presupuesto in presupuestos
        if presupuesto.fecha
    ]
    ultima_actividad = (
        max(fechas_actividad)
        if fechas_actividad
        else None
    )
    dias_sin_actividad = (
        (hoy - ultima_actividad).days
        if ultima_actividad
        else None
    )

    atenciones = []
    if pedidos_listos:
        atenciones.append(
            f"{len(pedidos_listos)} pedido(s) listo(s) para entregar"
        )
    if saldo_pendiente > 0:
        atenciones.append(
            f"Saldo pendiente de $ {saldo_pendiente:,.0f}"
        )
    if presupuestos_pendientes:
        atenciones.append(
            f"{len(presupuestos_pendientes)} presupuesto(s) pendiente(s)"
        )
    if entregas_proximas:
        atenciones.append(
            f"{len(entregas_proximas)} entrega(s) próxima(s)"
        )

    return {
        "cliente": cliente,
        "pedidos": pedidos,
        "presupuestos": presupuestos,
        "cantidad_pedidos": len(pedidos),
        "cantidad_cancelados": sum(
            1 for pedido in pedidos
            if pedido.estado == "CANCELADO"
        ),
        "pedidos_activos": pedidos_activos,
        "pedidos_activos_count": len(pedidos_activos),
        "pedidos_listos_count": len(pedidos_listos),
        "presupuestos_pendientes": presupuestos_pendientes,
        "presupuestos_pendientes_count": len(presupuestos_pendientes),
        "total_comprado": total_comprado,
        "total_pagado": total_pagado,
        "saldo_pendiente": saldo_pendiente,
        "ultimo_pedido": pedidos[0] if pedidos else None,
        "ultimo_presupuesto": presupuestos[0] if presupuestos else None,
        "ultima_actividad": ultima_actividad,
        "dias_sin_actividad": dias_sin_actividad,
        "sin_actividad_reciente": (
            dias_sin_actividad is None
            or dias_sin_actividad >= 60
        ),
        "atenciones": atenciones,
        "necesita_atencion": bool(atenciones),
        "whatsapp_url": _whatsapp_url(cliente),
    }


def lista_clientes(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()

    clientes = (
        Cliente.objects
        .filter(activo=True)
        .prefetch_related(
            Prefetch(
                "pedidos",
                queryset=_pedidos_cliente_queryset(),
                to_attr="pedidos_historial_cache",
            ),
            Prefetch(
                "presupuestos",
                queryset=_presupuestos_cliente_queryset(),
                to_attr="presupuestos_historial_cache",
            ),
        )
        .order_by("nombre")
    )

    if busqueda:
        clientes = clientes.filter(
            Q(nombre__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
            | Q(email__icontains=busqueda)
        )

    filas_base = [
        _resumen_cliente(
            cliente,
            cliente.pedidos_historial_cache,
            cliente.presupuestos_historial_cache,
        )
        for cliente in clientes
    ]

    metricas = {
        "total": len(filas_base),
        "con_pedidos": sum(
            1 for fila in filas_base
            if fila["pedidos_activos_count"] > 0
        ),
        "con_saldo": sum(
            1 for fila in filas_base
            if fila["saldo_pendiente"] > 0
        ),
        "con_presupuestos": sum(
            1 for fila in filas_base
            if fila["presupuestos_pendientes_count"] > 0
        ),
        "atencion": sum(
            1 for fila in filas_base
            if fila["necesita_atencion"]
        ),
        "sin_actividad": sum(
            1 for fila in filas_base
            if fila["sin_actividad_reciente"]
        ),
        "total_comprado": sum(
            (fila["total_comprado"] for fila in filas_base),
            Decimal("0"),
        ),
        "saldo_total": sum(
            (fila["saldo_pendiente"] for fila in filas_base),
            Decimal("0"),
        ),
    }

    filtros = {
        "pedidos": lambda fila: fila["pedidos_activos_count"] > 0,
        "saldo": lambda fila: fila["saldo_pendiente"] > 0,
        "presupuestos": lambda fila: (
            fila["presupuestos_pendientes_count"] > 0
        ),
        "atencion": lambda fila: fila["necesita_atencion"],
        "sin_actividad": lambda fila: fila["sin_actividad_reciente"],
    }

    if estado in filtros:
        filas = [
            fila for fila in filas_base
            if filtros[estado](fila)
        ]
    else:
        filas = filas_base

    filtro_urls = {
        "todos": _url_con_filtros(request, estado=None),
        "pedidos": _url_con_filtros(request, estado="pedidos"),
        "saldo": _url_con_filtros(request, estado="saldo"),
        "presupuestos": _url_con_filtros(
            request,
            estado="presupuestos",
        ),
        "atencion": _url_con_filtros(request, estado="atencion"),
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
        Cliente,
        id=cliente_id,
    )

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        email = request.POST.get("email", "").strip()
        observaciones = request.POST.get(
            "observaciones",
            "",
        ).strip()

        if not nombre:
            messages.error(
                request,
                "El nombre del cliente no puede quedar vacío.",
            )
            return redirect(f"{request.path}?editar=1")

        existente = buscar_cliente_por_telefono(
            telefono,
            excluir_id=cliente.id,
        )
        if existente:
            messages.error(
                request,
                (
                    f"Ese teléfono ya pertenece a {existente.nombre} "
                    f"({existente.codigo})."
                ),
            )
            return redirect(f"{request.path}?editar=1")

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

    pedidos = list(
        _pedidos_cliente_queryset()
        .filter(cliente=cliente)
    )
    presupuestos = list(
        _presupuestos_cliente_queryset()
        .filter(cliente=cliente)
    )
    resumen = _resumen_cliente(
        cliente,
        pedidos,
        presupuestos,
    )

    asignar_miniatura_resumen(pedidos, "detalles")
    asignar_miniatura_resumen(presupuestos, "detalles")

    filas_pedidos = []
    for pedido in pedidos:
        cancelado = pedido.estado == "CANCELADO"
        entregado = pedido.estado == "ENTREGADO"
        activo = not cancelado and not entregado
        saldo_modelo = pedido.saldo_pendiente

        preparacion = (
            _armar_preparacion(pedido)
            if activo
            else []
        )
        preparacion_total = len(preparacion)
        preparacion_listos = sum(
            1 for item in preparacion
            if item["listo"]
        )
        preparacion_porcentaje = (
            int(round(
                (preparacion_listos * 100)
                / preparacion_total
            ))
            if preparacion_total
            else 0
        )

        filas_pedidos.append(
            {
                "pedido": pedido,
                "total": pedido.total,
                "pagado": pedido.total_pagado,
                "saldo": (
                    Decimal("0")
                    if cancelado
                    else saldo_modelo
                ),
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
                    1 for item in preparacion
                    if item.get("estado_operativo") == "FALTANTE"
                ),
            }
        )

    eventos = []
    for pedido in pedidos:
        eventos.append(
            {
                "fecha": pedido.fecha,
                "tipo": "PEDIDO",
                "titulo": f"{pedido.codigo} · {pedido.get_estado_display()}",
                "detalle": f"Total $ {pedido.total:,.0f}",
            }
        )
        for pago in pedido.pagos.all():
            eventos.append(
                {
                    "fecha": pago.fecha.date(),
                    "tipo": "PAGO",
                    "titulo": f"Pago en {pedido.codigo}",
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
                "detalle": f"Total $ {presupuesto.total:,.0f}",
            }
        )

    eventos.sort(
        key=lambda evento: evento["fecha"],
        reverse=True,
    )

    return render(
        request,
        "clientes/detalle_v2.html",
        {
            "cliente": cliente,
            "filas_pedidos": filas_pedidos,
            "presupuestos": presupuestos,
            "eventos": eventos[:12],
            "modo_edicion": request.GET.get("editar") == "1",
            **resumen,
        },
    )
