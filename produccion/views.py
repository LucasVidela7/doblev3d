from datetime import datetime, timedelta

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from pedidos.models import Pedido
from productos.models import Producto

from .models import Impresora, Produccion


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
            timezone.get_current_timezone(),
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
    producciones = list(
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

    ahora = timezone.now()

    # Orden operativo:
    # 1. Lo que está IMPRIMIENDO.
    # 2. Lo PLANIFICADO/PENDIENTE, por horario más próximo.
    # 3. Lo LISTO, dejando lo más reciente arriba.
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
            and produccion.inicio_impresion is not None
            and produccion.inicio_impresion > ahora
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

    if impresora_id == "NUEVA":
        if not nueva_impresora_nombre:
            messages.error(
                request,
                (
                    "Ingresá el nombre de la "
                    "nueva impresora."
                ),
            )
            return redirect(
                "produccion:lista"
            )

        impresora, _ = (
            Impresora.objects
            .get_or_create(
                nombre=nueva_impresora_nombre,
                defaults={
                    "activa": True,
                },
            )
        )

        if not impresora.activa:
            impresora.activa = True
            impresora.save(
                update_fields=[
                    "activa",
                ]
            )

    else:
        if not impresora_id:
            messages.error(
                request,
                "Seleccioná una impresora.",
            )
            return redirect(
                "produccion:lista"
            )

        impresora = get_object_or_404(
            Impresora,
            id=impresora_id,
            activa=True,
        )

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
    # CONFLICTO DE AGENDA
    # --------------------------------------------------------

    conflicto = _conflicto_planificacion(
        impresora=impresora,
        inicio=inicio_impresion,
        tiempo_minutos=tiempo_total,
    )

    if conflicto:
        inicio_conflicto = (
            timezone.localtime(
                conflicto.inicio_impresion
            ).strftime(
                "%d/%m %H:%M"
            )
        )

        fin_conflicto = (
            timezone.localtime(
                conflicto.fin_estimado
            ).strftime(
                "%d/%m %H:%M"
            )
        )

        messages.error(
            request,
            (
                f"{impresora.nombre} ya tiene "
                f"{conflicto.codigo} programada "
                f"de {inicio_conflicto} a "
                f"{fin_conflicto}."
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
        produccion.inicio_impresion
    ).strftime(
        "%d/%m/%Y %H:%M"
    )

    fin_local = timezone.localtime(
        produccion.fin_estimado
    ).strftime(
        "%d/%m/%Y %H:%M"
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} planificada en "
            f"{impresora.nombre} para "
            f"{inicio_local}. "
            f"Fin estimado: {fin_local}."
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
            "impresora",
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

    if not produccion.impresora:
        messages.error(
            request,
            (
                "La producción no tiene una "
                "impresora asignada."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    # Se puede adelantar una producción.
    # Al mandarla a imprimir, el inicio real para esta
    # versión pasa a ser AHORA.
    inicio_actual = timezone.now()

    ocupando = _impresora_ocupada(
        impresora=produccion.impresora,
        excluir_id=produccion.id,
    )

    if ocupando:
        messages.error(
            request,
            (
                f"{produccion.impresora.nombre} "
                f"está ocupada por "
                f"{ocupando.codigo} · "
                f"{ocupando.producto.nombre}."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    conflicto = _conflicto_planificacion(
        impresora=produccion.impresora,
        inicio=inicio_actual,
        tiempo_minutos=(
            produccion
            .tiempo_impresion_minutos
        ),
        excluir_id=produccion.id,
    )

    if conflicto:
        inicio_conflicto = (
            timezone.localtime(
                conflicto.inicio_impresion
            ).strftime(
                "%d/%m %H:%M"
            )
        )

        messages.error(
            request,
            (
                "No se puede adelantar porque "
                f"se superpondría con "
                f"{conflicto.codigo} desde "
                f"{inicio_conflicto}."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    produccion.inicio_impresion = (
        inicio_actual
    )
    produccion.estado = "IMPRIMIENDO"

    produccion.save(
        update_fields=[
            "inicio_impresion",
            "estado",
        ]
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} enviada a "
            f"{produccion.impresora.nombre}. "
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
        .select_for_update()
        .select_related(
            "producto",
            "impresora",
            "pedido",
        ),
        id=produccion_id,
        estado="LISTO",
    )

    if not original.impresora:
        messages.error(
            request,
            (
                "La producción terminada no tiene "
                "una impresora asignada."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    ocupando = _impresora_ocupada(
        impresora=original.impresora,
    )

    if ocupando:
        messages.error(
            request,
            (
                f"{original.impresora.nombre} "
                f"está ocupada por "
                f"{ocupando.codigo} · "
                f"{ocupando.producto.nombre}."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    inicio_actual = timezone.now()

    conflicto = _conflicto_planificacion(
        impresora=original.impresora,
        inicio=inicio_actual,
        tiempo_minutos=(
            original
            .tiempo_impresion_minutos
        ),
    )

    if conflicto:
        inicio_conflicto = (
            timezone.localtime(
                conflicto.inicio_impresion
            ).strftime(
                "%d/%m %H:%M"
            )
        )

        messages.error(
            request,
            (
                "No se puede repetir ahora porque "
                f"se superpondría con "
                f"{conflicto.codigo} desde "
                f"{inicio_conflicto}."
            ),
        )
        return redirect(
            "produccion:lista"
        )

    nueva = Produccion.objects.create(
        producto=original.producto,
        cantidad=original.cantidad,
        impresora=original.impresora,
        destino=original.destino,
        pedido=original.pedido,
        estado="IMPRIMIENDO",
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
            f"{original.impresora.nombre} quedó "
            "en IMPRIMIENDO con horario actual."
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
        .select_for_update()
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
