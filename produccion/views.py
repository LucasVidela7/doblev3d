from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from pedidos.models import Pedido
from productos.models import Producto
from productos.miniaturas import asignar_miniaturas_productos

from .models import Impresora, ImpresoraEstadoBambu, Produccion


ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


# ============================================================
# HELPERS
# ============================================================

def _parsear_datetime_local(texto):
    if not texto:
        return None

    try:
        fecha = datetime.strptime(
            texto,
            "%Y-%m-%dT%H:%M",
        )
    except ValueError:
        return None

    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(
            fecha,
            ARGENTINA_TZ,
        )

    return fecha


def _conflicto_planificacion(
    impresora,
    inicio,
    tiempo_minutos,
    excluir_id=None,
):
    """
    Busca superposición con trabajos PENDIENTES o IMPRIMIENDO
    de la misma impresora.

    Regla de superposición:
        inicio_nuevo < fin_existente
        y
        fin_nuevo > inicio_existente
    """
    if not impresora or not inicio or tiempo_minutos <= 0:
        return None

    fin = inicio + timedelta(
        minutes=tiempo_minutos
    )

    qs = (
        Produccion.objects
        .filter(
            impresora=impresora,
            estado__in=[
                "PENDIENTE",
                "IMPRIMIENDO",
            ],
            inicio_impresion__isnull=False,
        )
        .select_related(
            "producto",
            "impresora",
        )
        .order_by(
            "inicio_impresion",
            "id",
        )
    )

    if excluir_id:
        qs = qs.exclude(
            id=excluir_id
        )

    for existente in qs:
        if not existente.fin_estimado:
            continue

        if (
            inicio < existente.fin_estimado
            and fin > existente.inicio_impresion
        ):
            return existente

    return None


def _tiempo_sugerido_produccion(producto, cantidad):
    """
    Prioriza un tiempo real ya utilizado para la misma cantidad.
    Si todavía no existe, usa el tiempo unitario del producto como
    estimación austera para no bloquear la planificación.
    """
    cantidad = max(int(cantidad or 0), 1)
    recomendado = obtener_tiempo_recomendado(
        producto,
        cantidad,
    )
    if recomendado:
        return int(recomendado)

    unitario = (
        int(producto.horas or 0) * 60
        + int(producto.minutos or 0)
    )
    if unitario <= 0:
        return 0

    return unitario * cantidad


def _formatear_minutos(total):
    total = max(int(total or 0), 0)
    if total <= 0:
        return "Sin tiempo estimado"

    horas, minutos = divmod(total, 60)
    if horas and minutos:
        return f"{horas} h {minutos} min"
    if horas:
        return f"{horas} h"
    return f"{minutos} min"


def _impresora_ocupada(
    impresora,
    excluir_id=None,
):
    if not impresora:
        return None

    qs = (
        Produccion.objects
        .filter(
            impresora=impresora,
            estado="IMPRIMIENDO",
        )
        .select_related(
            "producto",
            "impresora",
        )
        .order_by("id")
    )

    if excluir_id:
        qs = qs.exclude(
            id=excluir_id
        )

    return qs.first()


# ============================================================
# VÍNCULO BAMBU ↔ IMPRESORA
# ============================================================

@transaction.atomic
def vincular_impresora_bambu(request, estado_id):
    if request.method != "POST":
        return redirect("produccion:lista")

    estado_bambu = get_object_or_404(
        ImpresoraEstadoBambu,
        id=estado_id,
    )

    accion = (
        request.POST.get("accion", "VINCULAR")
        .strip()
        .upper()
    )

    if accion == "DESVINCULAR":
        estado_bambu.impresora = None
        estado_bambu.save(
            update_fields=["impresora"]
        )
        messages.success(
            request,
            "Impresora Bambu desvinculada.",
        )
        return redirect(
            reverse("produccion:lista") + "#ahora"
        )

    impresora_id = (
        request.POST.get("impresora", "")
        .strip()
    )

    if not impresora_id:
        messages.error(
            request,
            "Elegí una impresora para vincular.",
        )
        return redirect(
            reverse("produccion:lista") + "#bambu-en-vivo"
        )

    impresora = get_object_or_404(
        Impresora,
        id=impresora_id,
        activa=True,
    )

    (
        ImpresoraEstadoBambu.objects
        .filter(impresora=impresora)
        .exclude(id=estado_bambu.id)
        .update(impresora=None)
    )

    estado_bambu.impresora = impresora
    estado_bambu.save(
        update_fields=["impresora"]
    )

    messages.success(
        request,
        (
            f"{estado_bambu.nombre_bridge or estado_bambu.serial} "
            f"vinculada a {impresora.nombre}."
        ),
    )

    return redirect(
        reverse("produccion:lista") + "#ahora"
    )


# ============================================================
# LISTA DE PRODUCCIÓN
# ============================================================

def lista_produccion(request):
    from pedidos.impresiones_stock import obtener_impresiones_por_producto
    from pedidos.personalizados_produccion import sincronizar_personalizados_pendientes

    sincronizar_personalizados_pendientes()

    """
    Vista operativa de producción.

    Por defecto:
    - muestra SIEMPRE PENDIENTE e IMPRIMIENDO
    - suma las últimas 20 producciones LISTO
    - evita que el historial crezca indefinidamente en pantalla

    Filtros disponibles:
    - estado
    - impresora
    - texto de producto/código
    - fecha desde/hasta
    """

    ahora = timezone.now()
    inicio_de_hoy = timezone.make_aware(
        datetime.combine(
            timezone.localdate(
                ahora,
                ARGENTINA_TZ,
            ),
            datetime.min.time(),
        ),
        ARGENTINA_TZ,
    )

    # Una planificación de un día anterior ya no representa
    # un horario posible. La movemos al momento actual para que
    # el fin estimado vuelva a calcularse desde ahora.
    Produccion.objects.filter(
        estado="PENDIENTE",
        inicio_impresion__lt=inicio_de_hoy,
    ).update(
        inicio_impresion=ahora,
    )

    estado_filtro = (
        request.GET.get(
            "estado",
            "ACTIVAS",
        ).strip()
        or "ACTIVAS"
    )

    impresora_filtro = (
        request.GET.get(
            "impresora",
            "",
        ).strip()
    )

    busqueda = (
        request.GET.get(
            "q",
            "",
        ).strip()
    )

    fecha_desde = (
        request.GET.get(
            "desde",
            "",
        ).strip()
    )

    fecha_hasta = (
        request.GET.get(
            "hasta",
            "",
        ).strip()
    )

    qs_base = (
        Produccion.objects
        .select_related(
            "producto",
            "impresora",
            "pedido",
            "pedido__cliente",
        )
        .exclude(
            estado="CANCELADO"
        )
    )

    if impresora_filtro:
        qs_base = qs_base.filter(
            impresora_id=impresora_filtro
        )

    if busqueda:
        qs_base = qs_base.filter(
            Q(
                producto__nombre__icontains=
                    busqueda
            )
            |
            Q(
                producto__id__icontains=
                    busqueda.replace(
                        "P",
                        "",
                    ).replace(
                        "p",
                        "",
                    )
            )
        )

    if fecha_desde:
        try:
            desde_dt = datetime.strptime(
                fecha_desde,
                "%Y-%m-%d",
            )
            desde_dt = timezone.make_aware(
                desde_dt,
                ARGENTINA_TZ,
            )
            qs_base = qs_base.filter(
                inicio_impresion__gte=
                    desde_dt
            )
        except ValueError:
            pass

    if fecha_hasta:
        try:
            hasta_dt = datetime.strptime(
                fecha_hasta,
                "%Y-%m-%d",
            )
            hasta_dt = (
                hasta_dt
                + timedelta(days=1)
            )
            hasta_dt = timezone.make_aware(
                hasta_dt,
                ARGENTINA_TZ,
            )
            qs_base = qs_base.filter(
                inicio_impresion__lt=
                    hasta_dt
            )
        except ValueError:
            pass

    if estado_filtro == "PENDIENTE":
        producciones = list(
            qs_base
            .filter(
                estado="PENDIENTE"
            )
        )

    elif estado_filtro == "IMPRIMIENDO":
        producciones = list(
            qs_base
            .filter(
                estado="IMPRIMIENDO"
            )
        )

    elif estado_filtro == "LISTO":
        producciones = list(
            qs_base
            .filter(
                estado="LISTO"
            )
        )

    elif estado_filtro == "TODAS":
        producciones = list(
            qs_base
        )

    elif estado_filtro in ["ACTIVAS", "OPERATIVA"]:
        producciones = list(
            qs_base.filter(
                estado__in=[
                    "PENDIENTE",
                    "IMPRIMIENDO",
                ]
            )
        )
        estado_filtro = "ACTIVAS"

    else:
        producciones = list(
            qs_base.filter(
                estado__in=[
                    "PENDIENTE",
                    "IMPRIMIENDO",
                ]
            )
        )
        estado_filtro = "ACTIVAS"

    # Orden operativo:
    # 1. IMPRIMIENDO.
    # 2. PENDIENTE por horario próximo.
    # 3. LISTO más reciente primero.
    def clave_orden(produccion):
        if produccion.estado == "IMPRIMIENDO":
            return (
                0,
                produccion.inicio_impresion
                or ahora,
                produccion.id,
            )

        if produccion.estado == "PENDIENTE":
            return (
                1,
                produccion.inicio_impresion
                or ahora,
                produccion.id,
            )

        fecha = (
            produccion.inicio_impresion
            or ahora
        )

        return (
            2,
            -fecha.timestamp(),
            -produccion.id,
        )

    producciones.sort(
        key=clave_orden
    )

    for produccion in producciones:
        produccion.es_planificada_futura = (
            produccion.estado == "PENDIENTE"
            and produccion.inicio_impresion
                is not None
            and produccion.inicio_impresion
                > ahora
        )
        produccion.es_planificada_vencida = (
            produccion.estado == "PENDIENTE"
            and produccion.inicio_impresion
                is not None
            and produccion.inicio_impresion
                <= ahora
        )
        produccion.fin_si_inicia_ahora = (
            ahora
            + timedelta(
                minutes=
                    produccion.tiempo_impresion_minutos
            )
            if (
                produccion.es_planificada_vencida
                and produccion.tiempo_impresion_minutos
            )
            else None
        )

    productos = (
        Producto.objects
        .filter(
            activo=True,
            requiere_impresion=True,
        )
        .order_by(
            "nombre"
        )
    )

    impresoras = (
        Impresora.objects
        .filter(
            activa=True,
        )
        .order_by(
            "nombre"
        )
    )

    pedidos = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
        .select_related(
            "cliente"
        )
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    producto_seleccionado = (
        request.GET.get(
            "producto",
            "",
        ).strip()
    )

    cantidad_seleccionada = (
        request.GET.get(
            "cantidad",
            "1",
        ).strip()
    )

    producto_seleccionado_obj = None

    if producto_seleccionado:
        producto_seleccionado_obj = (
            productos.filter(
                id=producto_seleccionado
            ).first()
        )

    cantidad_imprimiendo = sum(
        1
        for p in producciones
        if p.estado == "IMPRIMIENDO"
    )

    cantidad_pendientes = sum(
        1
        for p in producciones
        if p.estado == "PENDIENTE"
    )

    cantidad_listas = sum(
        1
        for p in producciones
        if p.estado == "LISTO"
    )

    necesidades = list(
        obtener_impresiones_por_producto()
    )

    if busqueda:
        termino = busqueda.casefold()
        necesidades = [
            item
            for item in necesidades
            if (
                termino in item["producto"].nombre.casefold()
                or termino in item["producto"].codigo.casefold()
            )
        ]

    for item in necesidades:
        producto = item["producto"]
        falta = max(int(item.get("falta_iniciar") or 0), 0)
        peso_unitario = getattr(producto, "peso_gramos", 0) or 0
        item["peso_faltante_gramos"] = float(peso_unitario) * falta
        item["cantidad_sugerida"] = max(
            int(item.get("falta_normal_planificar") or 0),
            1,
        )

    total_falta_planificar = sum(
        max(int(item.get("falta_iniciar") or 0), 0)
        for item in necesidades
    )
    total_planificado_unidades = sum(
        max(int(item.get("planificadas") or 0), 0)
        for item in necesidades
    )
    total_imprimiendo_unidades = sum(
        max(int(item.get("en_produccion") or 0), 0)
        for item in necesidades
    )
    productos_con_necesidad = sum(
        1
        for item in necesidades
        if int(item.get("falta_iniciar") or 0) > 0
    )
    peso_faltante_gramos = sum(
        item["peso_faltante_gramos"]
        for item in necesidades
    )

    impresoras = list(impresoras)
    trabajos_imprimiendo_lista = list(
        Produccion.objects
        .filter(
            estado="IMPRIMIENDO",
            impresora__in=impresoras,
        )
        .select_related(
            "producto",
            "impresora",
            "pedido",
            "pedido__cliente",
        )
        .order_by(
            "inicio_impresion",
            "id",
        )
    )

    trabajos_imprimiendo = {
        trabajo.impresora_id: trabajo
        for trabajo in trabajos_imprimiendo_lista
        if trabajo.impresora_id
    }

    for impresora in impresoras:
        impresora.trabajo_actual = trabajos_imprimiendo.get(
            impresora.id
        )
        impresora.esta_libre = impresora.trabajo_actual is None

    impresoras_libres = sum(
        1 for impresora in impresoras
        if impresora.esta_libre
    )

    if peso_faltante_gramos >= 1000:
        peso_faltante_texto = (
            f"{peso_faltante_gramos / 1000:.2f}"
            .rstrip("0")
            .rstrip(".")
            + " kg"
        )
    else:
        peso_faltante_texto = (
            f"{peso_faltante_gramos:.0f} g"
        )

    necesidades_pendientes = [
        item
        for item in necesidades
        if int(item.get("falta_iniciar") or 0) > 0
    ]

    for indice, item in enumerate(necesidades_pendientes):
        cantidad_sugerida = max(
            int(item.get("falta_normal_planificar") or 0),
            0,
        )
        item["puede_planificar_rapido"] = cantidad_sugerida > 0
        item["cantidad_sugerida"] = cantidad_sugerida
        item["es_recomendada"] = indice == 0
        item["tiempo_sugerido_minutos"] = (
            _tiempo_sugerido_produccion(
                item["producto"],
                cantidad_sugerida,
            )
            if cantidad_sugerida > 0
            else 0
        )
        item["tiempo_sugerido_texto"] = _formatear_minutos(
            item["tiempo_sugerido_minutos"]
        )

    cola_pendiente = list(
        qs_base
        .filter(estado="PENDIENTE")
        .order_by(
            "inicio_impresion",
            "id",
        )
    )

    historial_reciente = list(
        Produccion.objects
        .filter(estado="LISTO")
        .select_related(
            "producto",
            "impresora",
            "pedido",
            "pedido__cliente",
        )
        .order_by("-fecha", "-id")[:12]
    )

    impresoras_libres_lista = [
        impresora
        for impresora in impresoras
        if impresora.esta_libre
    ]

    for posicion, impresora in enumerate(impresoras_libres_lista):
        impresora.siguiente_trabajo = (
            cola_pendiente[posicion]
            if posicion < len(cola_pendiente)
            else None
        )
        impresora.sugerencia_necesidad = (
            necesidades_pendientes[0]
            if (
                not impresora.siguiente_trabajo
                and necesidades_pendientes
            )
            else None
        )

    sugerencia_actual = (
        necesidades_pendientes[0]
        if necesidades_pendientes
        else None
    )

    productos_visibles = []
    productos_visibles.extend(
        produccion.producto
        for produccion in producciones
        if getattr(produccion, "producto", None)
    )
    productos_visibles.extend(
        item["producto"]
        for item in necesidades_pendientes
        if item.get("producto")
    )
    productos_visibles.extend(
        produccion.producto
        for produccion in cola_pendiente
        if getattr(produccion, "producto", None)
    )
    productos_visibles.extend(
        trabajo.producto
        for trabajo in trabajos_imprimiendo.values()
        if getattr(trabajo, "producto", None)
    )
    productos_visibles.extend(
        produccion.producto
        for produccion in historial_reciente
        if getattr(produccion, "producto", None)
    )

    asignar_miniaturas_productos(
        productos_visibles
    )

    ahora_input = timezone.localtime(
        ahora,
        ARGENTINA_TZ,
    ).strftime("%Y-%m-%dT%H:%M")

    # Telemetría recibida desde el Bambu Bridge. Cuando un serial
    # se vincula con una Impresora, el estado real se integra directamente
    # en la tarjeta operativa de esa máquina.
    bambu_estados = list(
        ImpresoraEstadoBambu.objects
        .select_related("impresora")
        .order_by("nombre_bridge", "serial")
    )

    bambu_por_impresora = {}

    for estado_bambu in bambu_estados:
        estado_bambu.sync_reciente = bool(
            estado_bambu.ultimo_contacto
            and (
                ahora - estado_bambu.ultimo_contacto
            ) <= timedelta(minutes=2)
        )

        restante = estado_bambu.minutos_restantes
        if restante is None:
            estado_bambu.restante_texto = "Sin dato"
        else:
            horas, minutos = divmod(
                max(int(restante), 0),
                60,
            )
            if horas and minutos:
                estado_bambu.restante_texto = (
                    f"{horas} h {minutos} min"
                )
            elif horas:
                estado_bambu.restante_texto = f"{horas} h"
            else:
                estado_bambu.restante_texto = f"{minutos} min"

        if estado_bambu.impresora_id:
            bambu_por_impresora[
                estado_bambu.impresora_id
            ] = estado_bambu

    for impresora in impresoras:
        impresora.bambu_estado = (
            bambu_por_impresora.get(
                impresora.id
            )
        )

    bambu_sin_vincular = [
        estado_bambu
        for estado_bambu in bambu_estados
        if not estado_bambu.impresora_id
    ]

    return render(
        request,
        "produccion/lista.html",
        {
            "producciones": producciones,
            "productos": productos,
            "impresoras": impresoras,
            "pedidos": pedidos,
            "producto_seleccionado":
                producto_seleccionado,
            "producto_seleccionado_obj":
                producto_seleccionado_obj,
            "cantidad_seleccionada":
                cantidad_seleccionada,

            "estado_filtro":
                estado_filtro,
            "impresora_filtro":
                impresora_filtro,
            "busqueda":
                busqueda,
            "fecha_desde":
                fecha_desde,
            "fecha_hasta":
                fecha_hasta,

            "cantidad_imprimiendo":
                cantidad_imprimiendo,
            "cantidad_pendientes":
                cantidad_pendientes,
            "cantidad_listas":
                cantidad_listas,

            "necesidades": necesidades,
            "necesidades_pendientes": necesidades_pendientes,
            "cola_pendiente": cola_pendiente,
            "trabajos_imprimiendo_lista": trabajos_imprimiendo_lista,
            "historial_reciente": historial_reciente,
            "impresoras_libres_lista": impresoras_libres_lista,
            "sugerencia_actual": sugerencia_actual,
            "total_falta_planificar": total_falta_planificar,
            "total_planificado_unidades": total_planificado_unidades,
            "total_imprimiendo_unidades": total_imprimiendo_unidades,
            "productos_con_necesidad": productos_con_necesidad,
            "peso_faltante_gramos": peso_faltante_gramos,
            "ahora_input": ahora_input,
            "impresoras_libres": impresoras_libres,
            "peso_faltante_texto": peso_faltante_texto,
            "bambu_estados": bambu_estados,
            "bambu_sin_vincular": bambu_sin_vincular,
        },
    )


# ============================================================
# ACCIÓN RÁPIDA DESDE "QUÉ IMPRIMIR"
# ============================================================

@transaction.atomic
def accion_rapida_necesidad(request):
    if request.method != "POST":
        return redirect("produccion:lista")

    from pedidos.impresiones_compuestas import (
        MARCA_PERSONALIZADO,
        _cantidad_personalizada_fisica,
        _cantidad_personalizada_ya_planificada,
    )
    from pedidos.impresiones_stock import obtener_impresiones_por_producto
    from pedidos.models import DetallePedido

    producto = get_object_or_404(
        Producto,
        id=request.POST.get("producto"),
        activo=True,
        requiere_impresion=True,
    )

    try:
        cantidad = int(request.POST.get("cantidad", "0"))
    except (TypeError, ValueError):
        cantidad = 0

    accion = (
        request.POST.get("accion", "PLANIFICAR")
        .strip()
        .upper()
    )
    personalizado_id = (
        request.POST.get("personalizado_id", "")
        .strip()
    )

    destino = "STOCK"
    pedido = None
    observaciones = (
        "Creada desde Centro de producción · acción rápida."
    )

    if personalizado_id:
        detalle = get_object_or_404(
            DetallePedido.objects
            .select_related("pedido", "producto")
            .prefetch_related("producto__componentes"),
            id=personalizado_id,
            tipo_item="PERSONALIZADO",
            estado="PENDIENTE",
        )
        total_fisico = _cantidad_personalizada_fisica(
            detalle,
            producto,
        )
        ya_planificado = _cantidad_personalizada_ya_planificada(
            detalle,
            producto,
        )
        restante = max(
            total_fisico - int(ya_planificado),
            0,
        )
        destino = "PEDIDO"
        pedido = detalle.pedido
        observaciones = (
            f"{MARCA_PERSONALIZADO}{detalle.id}\n"
            f"{detalle.pedido.codigo} · {detalle.producto.nombre}\n"
            f"Detalle: {detalle.detalle_personalizacion or 'Sin detalle'}\n"
            f"Color: {detalle.color_personalizacion or 'Sin color especificado'}"
        )
    else:
        item = next(
            (
                actual
                for actual in obtener_impresiones_por_producto()
                if actual["producto"].id == producto.id
            ),
            None,
        )
        restante = max(
            int(item.get("falta_normal_planificar") or 0)
            if item
            else 0,
            0,
        )

    if cantidad <= 0:
        messages.error(
            request,
            "Ingresá una cantidad mayor a cero.",
        )
        return redirect(
            reverse("produccion:lista") + "#prod-necesidad"
        )

    # Los trabajos personalizados están ligados a un pedido y no
    # deben exceder su faltante. La producción estándar, en cambio,
    # siempre puede superar la necesidad actual porque el excedente
    # queda destinado a STOCK.
    if personalizado_id and restante <= 0:
        messages.error(
            request,
            "Ese trabajo personalizado ya no tiene unidades por planificar.",
        )
        return redirect(
            reverse("produccion:lista") + "#prod-necesidad"
        )

    if personalizado_id and cantidad > restante:
        messages.error(
            request,
            f"Quedan {restante} unidad(es) personalizadas por cubrir.",
        )
        return redirect(
            reverse("produccion:lista") + "#prod-necesidad"
        )

    tiempo_total = _tiempo_sugerido_produccion(
        producto,
        cantidad,
    )

    if tiempo_total <= 0:
        messages.error(
            request,
            (
                f"{producto.nombre} no tiene tiempo de impresión configurado. "
                "Completalo en el producto o usá la planificación manual."
            ),
        )
        return redirect(
            reverse("produccion:lista") + "#prod-necesidad"
        )

    impresora = None
    estado = "PENDIENTE"
    inicio = timezone.now()

    if accion == "INICIAR":
        impresora_id = (
            request.POST.get("impresora", "")
            .strip()
        )
        if not impresora_id:
            messages.error(
                request,
                "Elegí una impresora libre para iniciar.",
            )
            return redirect(
                reverse("produccion:lista") + "#prod-necesidad"
            )

        impresora = get_object_or_404(
            Impresora,
            id=impresora_id,
            activa=True,
        )
        ocupando = _impresora_ocupada(impresora)
        if ocupando:
            messages.error(
                request,
                (
                    f"{impresora.nombre} está ocupada por "
                    f"{ocupando.producto.nombre}."
                ),
            )
            return redirect(
                reverse("produccion:lista") + "#ahora"
            )
        estado = "IMPRIMIENDO"
    elif accion != "PLANIFICAR":
        messages.error(
            request,
            "La acción solicitada no es válida.",
        )
        return redirect(
            reverse("produccion:lista") + "#prod-necesidad"
        )

    produccion = Produccion.objects.create(
        producto=producto,
        cantidad=cantidad,
        destino=destino,
        pedido=pedido,
        estado=estado,
        impresora=impresora,
        inicio_impresion=inicio,
        tiempo_impresion_minutos=tiempo_total,
        observaciones=observaciones,
    )

    if estado == "IMPRIMIENDO":
        messages.success(
            request,
            (
                f"{produccion.codigo} iniciada en {impresora.nombre}: "
                f"{producto.nombre} x{cantidad}."
            ),
        )
        return redirect(
            reverse("produccion:lista") + "#ahora"
        )

    messages.success(
        request,
        (
            f"{produccion.codigo} agregada a la cola: "
            f"{producto.nombre} x{cantidad}."
        ),
    )
    return redirect(
        reverse("produccion:lista") + "#prod-cola"
    )


# ============================================================
# PLANIFICAR DESDE DETALLE DE PRODUCTO
# ============================================================

@transaction.atomic
def planificar_desde_producto(request, producto_id):
    producto = get_object_or_404(
        Producto,
        id=producto_id,
        activo=True,
        requiere_impresion=True,
    )

    if request.method != "POST":
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    try:
        cantidad = int(
            request.POST.get("cantidad", "0")
        )
    except (TypeError, ValueError):
        cantidad = 0

    if cantidad <= 0:
        messages.error(
            request,
            "La cantidad a planificar debe ser mayor a cero.",
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    tiempo_total = _tiempo_sugerido_produccion(
        producto,
        cantidad,
    )

    if tiempo_total <= 0:
        messages.error(
            request,
            (
                f"{producto.nombre} no tiene tiempo de impresión "
                "configurado y tampoco existe una referencia histórica "
                f"para {cantidad} unidad(es)."
            ),
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    produccion = Produccion.objects.create(
        producto=producto,
        cantidad=cantidad,
        destino="STOCK",
        estado="PENDIENTE",
        impresora=None,
        inicio_impresion=timezone.now(),
        tiempo_impresion_minutos=tiempo_total,
        observaciones=(
            "Planificada desde el detalle del producto."
        ),
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} planificada: "
            f"{producto.nombre} x{cantidad}. "
            "Quedó agregada a la cola de producción."
        ),
    )

    return redirect(
        "productos:detalle",
        producto_id=producto.id,
    )


# ============================================================
# NUEVA PRODUCCIÓN / PLANIFICACIÓN
# ============================================================

@transaction.atomic
def nueva_produccion(request):
    if request.method != "POST":
        return redirect(
            "produccion:lista"
        )

    producto_id = (
        request.POST.get(
            "producto",
            "",
        ).strip()
    )

    cantidad_texto = (
        request.POST.get(
            "cantidad",
            "",
        ).strip()
    )

    impresora_id = (
        request.POST.get(
            "impresora",
            "",
        ).strip()
    )

    nueva_impresora_nombre = (
        request.POST.get(
            "nueva_impresora_nombre",
            "",
        ).strip()
    )

    destino = (
        request.POST.get(
            "destino",
            "",
        ).strip()
    )

    pedido_id = (
        request.POST.get(
            "pedido",
            "",
        ).strip()
    )

    inicio_texto = (
        request.POST.get(
            "inicio_impresion",
            "",
        ).strip()
    )

    horas_texto = (
        request.POST.get(
            "horas",
            "0",
        ).strip()
    )

    minutos_texto = (
        request.POST.get(
            "minutos",
            "0",
        ).strip()
    )

    # --------------------------------------------------------
    # PRODUCTO
    # --------------------------------------------------------

    if not producto_id:
        messages.error(
            request,
            (
                "Buscá un producto y seleccioná "
                "una opción válida."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    producto = get_object_or_404(
        Producto,
        id=producto_id,
        activo=True,
        requiere_impresion=True,
    )

    # --------------------------------------------------------
    # CANTIDAD
    # --------------------------------------------------------

    try:
        cantidad = int(
            cantidad_texto
        )
    except (
        TypeError,
        ValueError,
    ):
        cantidad = 0

    if cantidad <= 0:
        messages.error(
            request,
            "La cantidad debe ser mayor a 0.",
        )
        return redirect(
            "produccion:lista"
        )

    # --------------------------------------------------------
    # IMPRESORA
    # --------------------------------------------------------
    #
    # La impresora YA NO se asigna al planificar.
    # Se elige al momento de iniciar la producción.
    # --------------------------------------------------------

    impresora = None

    # --------------------------------------------------------
    # DESTINO / PEDIDO
    # --------------------------------------------------------

    if destino not in [
        "STOCK",
        "PEDIDO",
    ]:
        messages.error(
            request,
            "El destino seleccionado no es válido.",
        )
        return redirect(
            "produccion:lista"
        )

    pedido = None

    if destino == "PEDIDO":
        if not pedido_id:
            messages.error(
                request,
                "Debés seleccionar un pedido.",
            )
            return redirect(
                "produccion:lista"
            )

        pedido = get_object_or_404(
            Pedido,
            id=pedido_id,
        )

        if pedido.estado in [
            "ENTREGADO",
            "CANCELADO",
        ]:
            messages.error(
                request,
                (
                    "No se puede producir para un "
                    "pedido entregado o cancelado."
                ),
            )
            return redirect(
                "produccion:lista"
            )

    # --------------------------------------------------------
    # HORARIO PLANIFICADO
    # --------------------------------------------------------

    inicio_impresion = (
        _parsear_datetime_local(
            inicio_texto
        )
    )

    if inicio_impresion is None:
        messages.error(
            request,
            (
                "Ingresá una fecha y hora "
                "de inicio válida."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    ahora = timezone.now()
    if timezone.localdate(
        inicio_impresion,
        ARGENTINA_TZ,
    ) < timezone.localdate(
        ahora,
        ARGENTINA_TZ,
    ):
        inicio_impresion = ahora

    # --------------------------------------------------------
    # TIEMPO
    # --------------------------------------------------------

    if cantidad == 1:
        tiempo_total = (
            int(producto.horas or 0)
            * 60
            + int(producto.minutos or 0)
        )

        if tiempo_total <= 0:
            messages.error(
                request,
                (
                    "Este producto no tiene un "
                    "tiempo de impresión configurado."
                ),
            )
            return redirect(
                "produccion:lista"
            )

    else:
        try:
            horas = int(
                horas_texto or 0
            )
            minutos = int(
                minutos_texto or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            horas = -1
            minutos = -1

        if horas < 0:
            messages.error(
                request,
                (
                    "Las horas no pueden ser "
                    "negativas."
                ),
            )
            return redirect(
                "produccion:lista"
            )

        if (
            minutos < 0
            or minutos > 59
        ):
            messages.error(
                request,
                (
                    "Los minutos deben estar "
                    "entre 0 y 59."
                ),
            )
            return redirect(
                "produccion:lista"
            )

        tiempo_total = (
            horas * 60
            + minutos
        )

        if tiempo_total <= 0:
            tiempo_recomendado = (
                obtener_tiempo_recomendado(
                    producto,
                    cantidad,
                )
            )

            if tiempo_recomendado:
                tiempo_total = (
                    tiempo_recomendado
                )
            else:
                messages.error(
                    request,
                    (
                        "No existe un tiempo anterior "
                        f"para {producto.nombre} "
                        f"x{cantidad}. Ingresalo "
                        "manualmente."
                    ),
                )
                return redirect(
                    "produccion:lista"
                )

    # --------------------------------------------------------
    # CREAR PLANIFICACIÓN
    # --------------------------------------------------------

    produccion = (
        Produccion.objects.create(
            producto=producto,
            cantidad=cantidad,
            impresora=impresora,
            destino=destino,
            pedido=pedido,
            estado="PENDIENTE",
            inicio_impresion=
                inicio_impresion,
            tiempo_impresion_minutos=
                tiempo_total,
        )
    )

    inicio_local = timezone.localtime(
        produccion.inicio_impresion,
        ARGENTINA_TZ,
    ).strftime(
        "%d/%m/%Y %H:%M"
    )

    fin_local = timezone.localtime(
        produccion.fin_estimado,
        ARGENTINA_TZ,
    ).strftime(
        "%d/%m/%Y %H:%M"
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} planificada para "
            f"{inicio_local}. "
            f"Fin estimado: {fin_local}. "
            "La impresora se elige al comenzar."
        ),
    )

    return redirect(
        "produccion:lista"
    )


# ============================================================
# INICIAR PRODUCCIÓN PLANIFICADA
# ============================================================

@transaction.atomic
def iniciar_produccion(
    request,
    produccion_id,
):
    if request.method != "POST":
        return redirect(
            "produccion:lista"
        )

    produccion = get_object_or_404(
        Produccion.objects
        .select_for_update()
        .select_related(
            "producto",
        ),
        id=produccion_id,
    )

    if produccion.estado != "PENDIENTE":
        messages.error(
            request,
            (
                f"{produccion.codigo} ya no está "
                "pendiente."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    impresora_id = (
        request.POST.get(
            "impresora",
            "",
        ).strip()
    )

    if not impresora_id:
        messages.error(
            request,
            "Seleccioná una impresora para comenzar.",
        )
        return redirect(
            "produccion:lista"
        )

    impresora = get_object_or_404(
        Impresora,
        id=impresora_id,
        activa=True,
    )

    inicio_actual = timezone.now()

    ocupando = _impresora_ocupada(
        impresora=impresora,
        excluir_id=produccion.id,
    )

    if ocupando:
        messages.error(
            request,
            (
                f"{impresora.nombre} "
                f"está ocupada por "
                f"{ocupando.codigo} · "
                f"{ocupando.producto.nombre}."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    produccion.impresora = impresora
    produccion.inicio_impresion = (
        inicio_actual
    )
    produccion.estado = "IMPRIMIENDO"

    produccion.save(
        update_fields=[
            "impresora",
            "inicio_impresion",
            "estado",
        ]
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} enviada a "
            f"{impresora.nombre}. "
            "Inicio actualizado al horario actual."
        ),
    )

    return redirect(
        "produccion:lista"
    )


# ============================================================
# REPETIR PRODUCCIÓN TERMINADA
# ============================================================

@transaction.atomic
def repetir_produccion(
    request,
    produccion_id,
):
    if request.method != "POST":
        return redirect(
            "produccion:lista"
        )

    original = get_object_or_404(
        Produccion.objects
        .select_for_update(of=("self",))
        .select_related(
            "producto",
            "pedido",
        ),
        id=produccion_id,
        estado="LISTO",
    )

    inicio_actual = timezone.now()

    nueva = Produccion.objects.create(
        producto=original.producto,
        cantidad=original.cantidad,
        impresora=None,
        destino=original.destino,
        pedido=original.pedido,
        estado="PENDIENTE",
        inicio_impresion=inicio_actual,
        tiempo_impresion_minutos=(
            original
            .tiempo_impresion_minutos
        ),
    )

    messages.success(
        request,
        (
            f"{nueva.codigo} creada repitiendo "
            f"{original.codigo}. "
            "Quedó PLANIFICADA con horario actual; "
            "la impresora se elige al comenzar."
        ),
    )

    return redirect(
        "produccion:lista"
    )


# ============================================================
# CAMBIAR ESTADO
# ============================================================

@transaction.atomic
def cambiar_estado(
    request,
    produccion_id,
):
    if request.method != "POST":
        return redirect(
            "produccion:lista"
        )

    produccion = get_object_or_404(
        Produccion.objects
        .select_for_update(of=("self",))
        .select_related(
            "impresora",
            "producto",
        ),
        id=produccion_id,
    )

    nuevo_estado = (
        request.POST.get(
            "estado",
            "",
        ).strip()
    )

    if nuevo_estado not in [
        "PENDIENTE",
        "IMPRIMIENDO",
        "LISTO",
        "CANCELADO",
    ]:
        messages.error(
            request,
            "El estado seleccionado no es válido.",
        )
        return redirect(
            "produccion:lista"
        )

    # La transición planificada a IMPRIMIENDO se hace
    # por el botón específico, para validar horario y máquina.
    if (
        nuevo_estado == "IMPRIMIENDO"
        and produccion.estado == "PENDIENTE"
    ):
        messages.error(
            request,
            (
                "Para iniciar una planificación usá "
                "el botón MANDAR A IMPRIMIR."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    # --------------------------------------------------------
    # PASAR A LISTO
    # --------------------------------------------------------

    if (
        nuevo_estado == "LISTO"
        and produccion.estado != "LISTO"
    ):
        if (
            produccion.destino == "STOCK"
            and not produccion.ingresado_stock
        ):
            producto = (
                Producto.objects
                .select_for_update()
                .get(
                    id=produccion.producto_id
                )
            )

            producto.stock += (
                produccion.cantidad
            )

            producto.save(
                update_fields=[
                    "stock",
                ]
            )

            produccion.ingresado_stock = True

    # --------------------------------------------------------
    # REVERTIR LISTO
    # --------------------------------------------------------

    elif (
        produccion.estado == "LISTO"
        and nuevo_estado != "LISTO"
        and produccion.ingresado_stock
    ):
        producto = (
            Producto.objects
            .select_for_update()
            .get(
                id=produccion.producto_id
            )
        )

        if (
            producto.stock
            < produccion.cantidad
        ):
            messages.error(
                request,
                (
                    "No se puede revertir esta "
                    "producción porque el stock "
                    "actual es menor que la cantidad "
                    "que había ingresado."
                ),
            )
            return redirect(
                "produccion:lista"
            )

        producto.stock -= (
            produccion.cantidad
        )

        producto.save(
            update_fields=[
                "stock",
            ]
        )

        produccion.ingresado_stock = False

    produccion.estado = nuevo_estado

    produccion.save(
        update_fields=[
            "estado",
            "ingresado_stock",
        ]
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} actualizada a "
            f"{produccion.get_estado_display()}."
        ),
    )

    return redirect(
        "produccion:lista"
    )


# ============================================================
# TIEMPO RECOMENDADO
# ============================================================

def obtener_tiempo_recomendado(
    producto,
    cantidad,
):
    if cantidad == 1:
        tiempo_producto = (
            int(producto.horas or 0)
            * 60
            + int(producto.minutos or 0)
        )

        return (
            tiempo_producto
            if tiempo_producto > 0
            else None
        )

    ultima_produccion = (
        Produccion.objects
        .filter(
            producto=producto,
            cantidad=cantidad,
            tiempo_impresion_minutos__gt=0,
        )
        .exclude(
            estado="CANCELADO"
        )
        .order_by(
            "-fecha",
            "-id",
        )
        .first()
    )

    if ultima_produccion:
        return (
            ultima_produccion
            .tiempo_impresion_minutos
        )

    return None


# ============================================================
# API - TIEMPO RECOMENDADO
# ============================================================

def tiempo_recomendado(request):
    if request.method != "GET":
        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "Método no permitido.",
            },
            status=405,
        )

    producto_id = request.GET.get(
        "producto"
    )

    cantidad_texto = request.GET.get(
        "cantidad"
    )

    try:
        cantidad = int(
            cantidad_texto
        )
    except (
        TypeError,
        ValueError,
    ):
        cantidad = 0

    if (
        not producto_id
        or cantidad <= 0
    ):
        return JsonResponse(
            {
                "ok": False,
                "encontrado": False,
                "horas": 0,
                "minutos": 0,
                "total_minutos": 0,
                "origen": "SIN_DATOS",
                "mensaje": (
                    "Seleccioná un producto "
                    "y una cantidad válida."
                ),
            }
        )

    producto = get_object_or_404(
        Producto,
        id=producto_id,
        activo=True,
        requiere_impresion=True,
    )

    tiempo_total = (
        obtener_tiempo_recomendado(
            producto,
            cantidad,
        )
    )

    if not tiempo_total:
        return JsonResponse(
            {
                "ok": True,
                "encontrado": False,
                "horas": 0,
                "minutos": 0,
                "total_minutos": 0,
                "origen": "MANUAL",
                "mensaje": (
                    "No hay un tiempo anterior "
                    "registrado para este producto "
                    "y esta cantidad."
                ),
            }
        )

    horas = tiempo_total // 60
    minutos = tiempo_total % 60

    return JsonResponse(
        {
            "ok": True,
            "encontrado": True,
            "horas": horas,
            "minutos": minutos,
            "total_minutos": tiempo_total,
            "origen": (
                "PRODUCTO"
                if cantidad == 1
                else "HISTORIAL"
            ),
            "mensaje": (
                "Tiempo configurado en el producto."
                if cantidad == 1
                else (
                    "Último tiempo registrado "
                    "para esta cantidad."
                )
            ),
        }
    )
