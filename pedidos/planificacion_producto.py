from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from productos.models import Producto
from produccion.models import Produccion
from produccion.views import obtener_tiempo_recomendado

from .impresiones_compuestas import (
    MARCA_PERSONALIZADO,
    _cantidad_personalizada_fisica,
    _parsear_inicio,
    _tiempo_manual,
    obtener_impresiones_por_producto,
)
from .models import DetallePedido


def _cantidad_personalizada_cubierta(detalle, producto):
    """
    Para una personalización, una unidad ya planificada o ya terminada no debe
    volver a planificarse. Se consideran PENDIENTE, IMPRIMIENDO y LISTO.
    """
    marca = f"{MARCA_PERSONALIZADO}{detalle.id}"
    return int(
        Produccion.objects
        .filter(
            producto=producto,
            estado__in=["PENDIENTE", "IMPRIMIENDO", "LISTO"],
            observaciones__contains=marca,
        )
        .aggregate(total=Sum("cantidad"))
        .get("total")
        or 0
    )


def planificar_impresion_producto(request):
    """
    Planifica una placa desde Impresiones por producto.

    - Estándar: cantidad libre. Si supera la demanda pendiente, el excedente se
      produce con destino STOCK.
    - Personalizado: conserva el límite exacto del pedido para no fabricar una
      personalización de más ni mezclarla con stock genérico.
    """
    if request.method != "POST":
        return redirect("pedidos:impresiones_productos")

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

    if cantidad <= 0:
        messages.error(request, "Ingresá una cantidad mayor a cero para la placa.")
        return redirect("pedidos:impresiones_productos")

    inicio = _parsear_inicio(
        request.POST.get("inicio_impresion", "").strip()
    )
    if inicio is None:
        messages.error(request, "Ingresá un día y horario válido para la planificación.")
        return redirect("pedidos:impresiones_productos")

    if inicio < timezone.now():
        inicio = timezone.now()

    personalizado_id = request.POST.get("personalizado_id", "").strip()
    destino = "STOCK"
    pedido = None
    restante = 0
    observaciones = "Planificada desde Impresiones por producto."

    if personalizado_id:
        detalle = get_object_or_404(
            DetallePedido.objects
            .select_related("pedido", "producto")
            .prefetch_related("producto__componentes"),
            id=personalizado_id,
            tipo_item="PERSONALIZADO",
            estado="PENDIENTE",
        )

        total_fisico = _cantidad_personalizada_fisica(detalle, producto)
        ya_cubierto = _cantidad_personalizada_cubierta(detalle, producto)
        restante = max(total_fisico - ya_cubierto, 0)

        if total_fisico <= 0:
            messages.error(
                request,
                "Ese producto no corresponde a la personalización seleccionada.",
            )
            return redirect("pedidos:impresiones_productos")

        if restante <= 0:
            messages.error(
                request,
                "Esa parte de la personalización ya está completamente cubierta.",
            )
            return redirect("pedidos:impresiones_productos")

        if cantidad > restante:
            messages.error(
                request,
                (
                    f"Para {detalle.pedido.codigo} quedan {restante} unidad(es) "
                    "personalizadas por planificar."
                ),
            )
            return redirect("pedidos:impresiones_productos")

        destino = "PEDIDO"
        pedido = detalle.pedido
        detalle_texto = detalle.detalle_personalizacion or "Sin detalle"
        color_texto = detalle.color_personalizacion or "Sin color especificado"
        observaciones = (
            f"{MARCA_PERSONALIZADO}{detalle.id}\n"
            f"{detalle.pedido.codigo} · {detalle.producto.nombre}\n"
            f"Detalle: {detalle_texto}\n"
            f"Color: {color_texto}"
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
        restante = int(item["falta_normal_planificar"] if item else 0)
        excedente = max(cantidad - restante, 0)

        observaciones = (
            "Planificada desde Impresiones por producto.\n"
            f"Demanda estándar pendiente al planificar: {restante}."
        )
        if excedente > 0:
            observaciones += (
                f"\nExcedente voluntario para stock: {excedente}."
            )

    tiempo_total = _tiempo_manual(request)

    if tiempo_total == -1:
        messages.error(
            request,
            "La duración debe tener horas válidas y minutos entre 0 y 59.",
        )
        return redirect("pedidos:impresiones_productos")

    if not tiempo_total:
        tiempo_total = obtener_tiempo_recomendado(
            producto,
            cantidad,
        )

    if not tiempo_total:
        messages.error(
            request,
            (
                f"No hay un tiempo registrado para {producto.nombre} x{cantidad}. "
                "Ingresá la duración estimada de esa placa."
            ),
        )
        return redirect("pedidos:impresiones_productos")

    produccion = Produccion.objects.create(
        producto=producto,
        cantidad=cantidad,
        destino=destino,
        pedido=pedido,
        estado="PENDIENTE",
        impresora=None,
        inicio_impresion=inicio,
        tiempo_impresion_minutos=tiempo_total,
        observaciones=observaciones,
    )

    if personalizado_id:
        mensaje_extra = ""
    else:
        excedente = max(cantidad - restante, 0)
        mensaje_extra = (
            f" {excedente} unidad(es) quedarán destinadas a aumentar stock."
            if excedente > 0
            else ""
        )

    messages.success(
        request,
        (
            f"{produccion.codigo} planificada: {producto.nombre} x{cantidad}. "
            f"La impresora se elige al momento de iniciar.{mensaje_extra}"
        ),
    )
    return redirect("pedidos:impresiones_productos")
