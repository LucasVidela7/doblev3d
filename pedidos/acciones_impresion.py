from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
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

    Si el cambio viene desde Preparación por AJAX, responde JSON para que
    la interfaz actualice el check sin recargar la página.
    """
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    es_ajax = (
        request.headers.get("X-Requested-With")
        == "XMLHttpRequest"
    )

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
        mensaje = "No se puede modificar un pedido entregado o cancelado."
        if es_ajax:
            return JsonResponse(
                {
                    "ok": False,
                    "mensaje": mensaje,
                },
                status=409,
            )

        messages.error(
            request,
            mensaje,
        )
        return redirect("pedidos:impresiones")

    marcar_listo = request.POST.get("listo") == "1"
    nuevo_estado = "LISTO" if marcar_listo else "PENDIENTE"

    if detalle.estado != nuevo_estado:
        DetallePedido.objects.filter(pk=detalle.pk).update(estado=nuevo_estado)
        detalle.estado = nuevo_estado

    actualizar_estado_general_pedido(pedido)

    nombre_producto = detalle.producto.nombre if detalle.producto else "Personalizado"
    mensaje = (
        f"{nombre_producto} personalizado marcado como "
        f"{'LISTO' if marcar_listo else 'PENDIENTE'}."
    )

    if es_ajax:
        pedido.refresh_from_db(
            fields=["estado"]
        )
        return JsonResponse(
            {
                "ok": True,
                "listo": marcar_listo,
                "personalizado": True,
                "pedido_estado": pedido.estado,
                "mensaje": mensaje,
            }
        )

    messages.success(
        request,
        mensaje,
    )
    return redirect("pedidos:impresiones")

