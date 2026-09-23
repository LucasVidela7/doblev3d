from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from productos.models import ConfiguracionCatalogo
from productos.whatsapp import whatsapp_url

from .models import Pedido


def _nombre_detalle(detalle):
    if detalle.tipo_item == "KIT":
        if detalle.kit:
            return detalle.kit.nombre
        snapshot = detalle.kit_snapshot or {}
        return snapshot.get("nombre") or "Kit"

    if detalle.tipo_item == "PERSONALIZADO":
        nombre = detalle.producto.nombre if detalle.producto else "Producto"
        return f"{nombre} personalizado"

    if detalle.producto:
        return detalle.producto.nombre

    return detalle.get_tipo_item_display()


@never_cache
def pedido_publico(request, token):
    """Detalle público de un pedido accesible sólo mediante token UUID."""
    pedido = get_object_or_404(
        Pedido.objects
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        ),
        public_token=token,
    )

    items = []
    for detalle in pedido.detalles.all():
        items.append(
            {
                "cantidad": detalle.cantidad,
                "nombre": _nombre_detalle(detalle),
                "subtotal": detalle.subtotal,
                "personalizacion": (
                    detalle.detalle_personalizacion
                    if detalle.tipo_item == "PERSONALIZADO"
                    else ""
                ),
                "color": detalle.color_personalizacion,
                "seleccion": [
                    {
                        "cantidad": item.cantidad,
                        "nombre": item.producto.nombre,
                    }
                    for item in detalle.productos_kit.all()
                ],
            }
        )

    config = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )
    mensaje = (
        f"Hola! Te consulto por mi pedido {pedido.codigo} "
        "de Doble V 3D."
    )
    nombre = (
        (pedido.cliente.nombre or "").strip().split()[0]
        if pedido.cliente_id
        else ""
    )

    return render(
        request,
        "pedidos/pedido_publico.html",
        {
            "pedido": pedido,
            "items": items,
            "cliente_nombre": nombre,
            "whatsapp_consulta_url": whatsapp_url(
                config.whatsapp_numero,
                mensaje,
            ),
        },
    )
