from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from . import views
from .models import DetallePedido, Pedido
from .personalizados_produccion import actualizar_estado_general_pedido


@transaction.atomic
def cambiar_listo_impresion(request):
    """
    Entrada estable para confirmar productos de un pedido.

    Los personalizados no consumen stock general: su confirmación actualiza
    directamente DetallePedido. Para productos normales/kits se delega en la
    lógica histórica, que mantiene el descuento/restauración de stock.

    El detalle se bloquea sin select_related() porque producto es una FK
    nullable. PostgreSQL no permite FOR UPDATE sobre el lado nullable de un
    outer join, que era la causa del error 500 al confirmar personalizados.
    """
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    detalle_id = (request.POST.get("detalle_personalizado_id") or "").strip()
    if not detalle_id:
        return views.cambiar_listo_impresion(request)

    detalle = get_object_or_404(
        DetallePedido.objects.select_for_update(),
        id=detalle_id,
        tipo_item="PERSONALIZADO",
    )

    pedido = Pedido.objects.select_for_update().get(pk=detalle.pedido_id)

    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(
            request,
            "No se puede modificar un pedido entregado o cancelado.",
        )
        return redirect("pedidos:impresiones")

    marcar_listo = request.POST.get("listo") == "1"
    nuevo_estado = "LISTO" if marcar_listo else "PENDIENTE"

    if detalle.estado != nuevo_estado:
        DetallePedido.objects.filter(pk=detalle.pk).update(estado=nuevo_estado)
        detalle.estado = nuevo_estado

    actualizar_estado_general_pedido(pedido)

    nombre_producto = detalle.producto.nombre if detalle.producto else "Personalizado"
    messages.success(
        request,
        (
            f"{nombre_producto} personalizado marcado como "
            f"{'LISTO' if marcar_listo else 'PENDIENTE'}."
        ),
    )
    return redirect("pedidos:impresiones")
