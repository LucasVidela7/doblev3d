from .image_environment import entorno_imagenes
from .image_models import ProductoImagen


def asignar_miniaturas_productos(productos):
    """Adjunta una URL de miniatura a productos ya cargados sin N+1 queries."""
    productos_unicos = {}

    for producto in productos:
        if not producto or not getattr(producto, "id", None):
            continue
        productos_unicos[producto.id] = producto

    if not productos_unicos:
        return {}

    imagenes = (
        ProductoImagen.objects
        .filter(
            producto_id__in=productos_unicos.keys(),
            ambiente=entorno_imagenes(),
            orden=1,
        )
        .values(
            "producto_id",
            "thumbnail_url",
            "url",
        )
    )

    urls = {
        item["producto_id"]: (
            item["thumbnail_url"]
            or item["url"]
            or ""
        )
        for item in imagenes
    }

    for producto_id, producto in productos_unicos.items():
        producto.imagen_produccion_url = urls.get(
            producto_id,
            "",
        )

    return urls
