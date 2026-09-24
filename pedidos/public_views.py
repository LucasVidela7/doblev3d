from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from productos.image_environment import entorno_imagenes
from productos.image_models import ProductoImagen
from productos.models import ConfiguracionCatalogo
from productos.whatsapp import whatsapp_url

from .adicionales import enriquecer_detalles_pedido
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
        .select_related(
            "cliente",
            "presupuesto_origen",
            "presupuesto_origen__solicitud_web_origen",
        )
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
            "presupuesto_origen__solicitud_web_origen__items",
            "pagos",
        ),
        public_token=token,
    )

    detalles = enriquecer_detalles_pedido(
        pedido,
        list(pedido.detalles.all()),
    )

    productos_por_detalle = {}
    ids_productos = set()

    for detalle in detalles:
        productos = []

        if detalle.producto_id and detalle.producto:
            productos.append(detalle.producto)

        if detalle.tipo_item == "KIT":
            seleccion = [
                item.producto
                for item in detalle.productos_kit.all()
                if item.producto_id and item.producto
            ]
            if seleccion:
                productos.extend(seleccion)
            elif detalle.kit_id and detalle.kit:
                productos.extend(
                    componente.producto
                    for componente in detalle.kit.componentes.all()
                    if componente.producto_id and componente.producto
                )

        unicos = []
        ids_vistos = set()
        for producto in productos:
            if producto.id in ids_vistos:
                continue
            ids_vistos.add(producto.id)
            unicos.append(producto)
            ids_productos.add(producto.id)

        productos_por_detalle[detalle.id] = unicos

    imagen_principal_por_producto = {
        imagen.producto_id: (imagen.url or imagen.thumbnail_url)
        for imagen in (
            ProductoImagen.objects
            .filter(
                producto_id__in=ids_productos,
                ambiente=entorno_imagenes(),
                orden=1,
            )
            .order_by("producto_id", "id")
        )
        if (imagen.url or imagen.thumbnail_url)
    }

    items = []
    for detalle in detalles:
        productos = productos_por_detalle.get(detalle.id, [])
        imagenes = []

        if detalle.tipo_item == "KIT":
            principales = [
                imagen_principal_por_producto[producto.id]
                for producto in productos
                if imagen_principal_por_producto.get(producto.id)
            ]
            imagenes = (
                principales[:4]
                if len(principales) >= 4
                else principales[:1]
            )
        elif productos:
            principal = imagen_principal_por_producto.get(
                productos[0].id,
                "",
            )
            imagenes = [principal] if principal else []

        items.append(
            {
                "cantidad": detalle.cantidad,
                "nombre": _nombre_detalle(detalle),
                "subtotal": detalle.subtotal,
                "precio_unitario": detalle.precio_unitario,
                "adicionales": detalle.adicionales,
                "imagenes": imagenes,
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
