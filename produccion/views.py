from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from pedidos.models import Pedido
from productos.models import Producto

from .models import Impresora, Produccion


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
    trabajos_imprimiendo = {
        trabajo.impresora_id: trabajo
        for trabajo in (
            Produccion.objects
            .filter(
                estado="IMPRIMIENDO",
                impresora__in=impresoras,
            )
            .select_related("producto", "impresora")
            .order_by("id")
        )
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

    ahora_input = timezone.localtime(
        ahora,
        ARGENTINA_TZ,
    ).strftime("%Y-%m-%dT%H:%M")

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
            "total_falta_planificar": total_falta_planificar,
            "total_planificado_unidades": total_planificado_unidades,
            "total_imprimiendo_unidades": total_imprimiendo_unidades,
            "productos_con_necesidad": productos_con_necesidad,
            "peso_faltante_gramos": peso_faltante_gramos,
            "ahora_input": ahora_input,
            "impresoras_libres": impresoras_libres,
            "peso_faltante_texto": peso_faltante_texto,
        },
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
