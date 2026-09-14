from datetime import datetime

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from pedidos.models import Pedido
from productos.models import Producto

from .models import Impresora, Produccion


# ============================================================
# LISTA DE PRODUCCIÓN
# ============================================================

def lista_produccion(request):
    producciones = (
        Produccion.objects
        .select_related(
            "producto",
            "pedido",
            "pedido__cliente",
            "impresora",
        )
        .exclude(
            estado="CANCELADO"
        )
        .order_by(
            "-fecha",
            "-id",
        )
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

    impresoras = (
        Impresora.objects
        .filter(activa=True)
        .order_by("nombre")
    )

    producto_seleccionado = request.GET.get(
        "producto",
        ""
    )

    cantidad_seleccionada = request.GET.get(
        "cantidad",
        "1"
    )

    return render(
        request,
        "produccion/lista.html",
        {
            "producciones": producciones,
            "productos": productos,
            "pedidos": pedidos,
            "impresoras": impresoras,
            "producto_seleccionado": producto_seleccionado,
            "cantidad_seleccionada": cantidad_seleccionada,
        }
    )


# ============================================================
# NUEVA PRODUCCIÓN
# ============================================================

@transaction.atomic
def nueva_produccion(request):
    if request.method != "POST":
        return redirect(
            "produccion:lista"
        )

    # --------------------------------------------------------
    # DATOS GENERALES
    # --------------------------------------------------------

    producto_id = request.POST.get(
        "producto"
    )

    cantidad_texto = request.POST.get(
        "cantidad"
    )

    destino = request.POST.get(
        "destino"
    )

    impresora_id = request.POST.get(
        "impresora",
        "",
    ).strip()

    nueva_impresora_nombre = request.POST.get(
        "nueva_impresora_nombre",
        "",
    ).strip()

    pedido_id = request.POST.get(
        "pedido"
    )

    inicio_texto = request.POST.get(
        "inicio_impresion",
        ""
    ).strip()

    horas_texto = request.POST.get(
        "horas",
        "0"
    )

    minutos_texto = request.POST.get(
        "minutos",
        "0"
    )

    observaciones = request.POST.get(
        "observaciones",
        ""
    ).strip()

    # --------------------------------------------------------
    # PRODUCTO
    # --------------------------------------------------------

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

    except (TypeError, ValueError):

        cantidad = 0

    if cantidad <= 0:
        messages.error(
            request,
            "La cantidad debe ser mayor a 0."
        )

        return redirect(
            "produccion:lista"
        )


    # --------------------------------------------------------
    # IMPRESORA
    # --------------------------------------------------------

    impresora = None

    if impresora_id == "NUEVA":
        if not nueva_impresora_nombre:
            messages.error(
                request,
                "Ingresá el nombre de la nueva impresora."
            )

            return redirect(
                "produccion:lista"
            )

        impresora, _ = (
            Impresora.objects.get_or_create(
                nombre=nueva_impresora_nombre,
                defaults={
                    "activa": True,
                },
            )
        )

        if not impresora.activa:
            impresora.activa = True
            impresora.save(
                update_fields=["activa"]
            )

    elif impresora_id:
        impresora = get_object_or_404(
            Impresora,
            id=impresora_id,
            activa=True,
        )

    else:
        messages.error(
            request,
            "Debés seleccionar una impresora."
        )

        return redirect(
            "produccion:lista"
        )

    # --------------------------------------------------------
    # DESTINO
    # --------------------------------------------------------

    if destino not in [
        "STOCK",
        "PEDIDO",
    ]:
        messages.error(
            request,
            "El destino seleccionado no es válido."
        )

        return redirect(
            "produccion:lista"
        )

    # --------------------------------------------------------
    # PEDIDO
    # --------------------------------------------------------

    pedido = None

    if destino == "PEDIDO":

        if not pedido_id:
            messages.error(
                request,
                "Debés seleccionar un pedido."
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
                "No se puede producir para un pedido "
                "entregado o cancelado."
            )

            return redirect(
                "produccion:lista"
            )

    # --------------------------------------------------------
    # INICIO DE IMPRESIÓN
    # --------------------------------------------------------

    if not inicio_texto:
        messages.error(
            request,
            "Debés ingresar la fecha y hora "
            "de inicio de impresión."
        )

        return redirect(
            "produccion:lista"
        )

    try:

        inicio_impresion = datetime.strptime(
            inicio_texto,
            "%Y-%m-%dT%H:%M"
        )

        if timezone.is_naive(
                inicio_impresion
        ):
            inicio_impresion = (
                timezone.make_aware(
                    inicio_impresion,
                    timezone.get_current_timezone()
                )
            )


    except ValueError:

        messages.error(
            request,
            "La fecha y hora de inicio "
            "no tienen un formato válido."
        )

        return redirect(
            "produccion:lista"
        )

    # --------------------------------------------------------
    # TIEMPO DE IMPRESIÓN
    # --------------------------------------------------------
    #
    # 1 unidad:
    # toma automáticamente el tiempo del producto.
    #
    # Más de 1 unidad:
    # tiempo ingresado manualmente.
    # --------------------------------------------------------

    if cantidad == 1:

        tiempo_total = (
                int(producto.horas) * 60
                + int(producto.minutos)
        )

        if tiempo_total <= 0:
            messages.error(
                request,
                "Este producto no tiene un tiempo "
                "de impresión configurado."
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

        except (TypeError, ValueError):

            messages.error(
                request,
                "El tiempo de impresión "
                "no es válido."
            )

            return redirect(
                "produccion:lista"
            )

        if horas < 0:
            messages.error(
                request,
                "Las horas no pueden ser negativas."
            )

            return redirect(
                "produccion:lista"
            )

        if minutos < 0 or minutos > 59:
            messages.error(
                request,
                "Los minutos deben estar "
                "entre 0 y 59."
            )

            return redirect(
                "produccion:lista"
            )

        tiempo_total = (
            horas * 60
            + minutos
        )

        # Si no llegó un tiempo manual válido,
        # intentamos recuperar el último registrado
        # para el mismo producto y la misma cantidad.
        if tiempo_total <= 0:

            tiempo_recomendado = obtener_tiempo_recomendado(
                producto,
                cantidad,
            )

            if tiempo_recomendado:

                tiempo_total = tiempo_recomendado

            else:

                messages.error(
                    request,
                    (
                        "No existe un tiempo anterior para "
                        f"{producto.nombre} x{cantidad}. "
                        "Debés ingresar el tiempo manualmente."
                    )
                )

                return redirect(
                    "produccion:lista"
                )


    # --------------------------------------------------------
    # CREAR PRODUCCIÓN
    # --------------------------------------------------------

    produccion = Produccion.objects.create(

        producto=producto,

        cantidad=cantidad,

        destino=destino,

        pedido=pedido,

        impresora=impresora,

        estado="PENDIENTE",

        inicio_impresion=inicio_impresion,

        tiempo_impresion_minutos=tiempo_total,

        observaciones=observaciones,
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} creada correctamente. "
            f"Finalización estimada: "
            f"{timezone.localtime(produccion.fin_estimado).strftime('%d/%m/%Y %H:%M')}."
        )
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
        produccion_id
):
    if request.method != "POST":
        return redirect(
            "produccion:lista"
        )

    produccion = get_object_or_404(
        Produccion.objects.select_for_update(),
        id=produccion_id,
    )

    nuevo_estado = request.POST.get(
        "estado"
    )

    if nuevo_estado not in [
        "PENDIENTE",
        "IMPRIMIENDO",
        "LISTO",
        "CANCELADO",
    ]:
        messages.error(
            request,
            "El estado seleccionado no es válido."
        )

        return redirect(
            "produccion:lista"
        )


    # ========================================================
    # PASAR A IMPRIMIENDO
    # ========================================================

    if (
        nuevo_estado == "IMPRIMIENDO"
        and produccion.estado != "IMPRIMIENDO"
    ):
        if not produccion.impresora_id:
            messages.error(
                request,
                (
                    f"{produccion.codigo} no tiene impresora asignada. "
                    "Editá o recreá la producción asignando una impresora."
                )
            )

            return redirect(
                "produccion:lista"
            )

        ocupada = (
            Produccion.objects
            .select_for_update()
            .filter(
                impresora_id=produccion.impresora_id,
                estado="IMPRIMIENDO",
            )
            .exclude(
                id=produccion.id,
            )
            .select_related(
                "producto",
            )
            .first()
        )

        if ocupada:
            messages.error(
                request,
                (
                    f"{produccion.impresora.nombre} ya está imprimiendo "
                    f"{ocupada.producto.nombre} "
                    f"({ocupada.codigo})."
                )
            )

            return redirect(
                "produccion:lista"
            )

    # ========================================================
    # PASAR A LISTO
    # ========================================================

    if (
            nuevo_estado == "LISTO"
            and produccion.estado != "LISTO"
    ):

        # ----------------------------------------------------
        # DESTINO STOCK
        # ----------------------------------------------------
        #
        # Se suma stock únicamente una vez.
        # ----------------------------------------------------

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
                    "stock"
                ]
            )

            produccion.ingresado_stock = True

        # ----------------------------------------------------
        # DESTINO PEDIDO
        # ----------------------------------------------------
        #
        # No toca stock general.
        # La impresión fue realizada específicamente
        # para ese pedido.
        # ----------------------------------------------------


    # ========================================================
    # REVERTIR LISTO
    # ========================================================

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

        if producto.stock < produccion.cantidad:
            messages.error(
                request,
                (
                    "No se puede revertir esta producción "
                    "porque el stock actual es menor que "
                    "la cantidad que había ingresado."
                )
            )

            return redirect(
                "produccion:lista"
            )

        producto.stock -= (
            produccion.cantidad
        )

        producto.save(
            update_fields=[
                "stock"
            ]
        )

        produccion.ingresado_stock = False

    # ========================================================
    # GUARDAR NUEVO ESTADO
    # ========================================================

    produccion.estado = (
        nuevo_estado
    )

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
        )
    )

    return redirect(
        "produccion:lista"
    )



# ============================================================
# TIEMPO RECOMENDADO
# ============================================================

def obtener_tiempo_recomendado(producto, cantidad):
    """
    Devuelve el tiempo recomendado en minutos.

    Cantidad = 1:
        usa horas/minutos configurados en Producto.

    Cantidad > 1:
        usa la última producción NO CANCELADA del mismo
        producto y la misma cantidad que tenga un tiempo válido.

    Si no existe referencia:
        devuelve None.
    """

    if cantidad == 1:

        tiempo_producto = (
            int(producto.horas or 0) * 60
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
                "mensaje": "Método no permitido.",
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

    except (TypeError, ValueError):

        cantidad = 0

    if not producto_id or cantidad <= 0:

        return JsonResponse(
            {
                "ok": False,
                "encontrado": False,
                "horas": 0,
                "minutos": 0,
                "total_minutos": 0,
                "origen": "SIN_DATOS",
                "mensaje": (
                    "Seleccioná un producto y una cantidad válida."
                ),
            }
        )

    producto = get_object_or_404(
        Producto,
        id=producto_id,
        activo=True,
        requiere_impresion=True,
    )

    tiempo_total = obtener_tiempo_recomendado(
        producto,
        cantidad,
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
                    "No hay un tiempo anterior registrado "
                    "para este producto y esta cantidad."
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
                else "Último tiempo registrado para esta cantidad."
            ),
        }
    )
