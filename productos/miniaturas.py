from .image_environment import entorno_imagenes
from .image_models import ProductoImagen


def asignar_miniaturas_productos(productos):
    """Adjunta una URL de miniatura a productos ya cargados sin N+1 queries."""
    productos_por_id = {}

    for producto in productos:
        if not producto or not getattr(producto, "id", None):
            continue
        productos_por_id.setdefault(producto.id, []).append(producto)

    if not productos_por_id:
        return {}

    imagenes = (
        ProductoImagen.objects
        .filter(
            producto_id__in=productos_por_id.keys(),
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

    for producto_id, instancias in productos_por_id.items():
        url = urls.get(producto_id, "")
        for producto in instancias:
            producto.imagen_produccion_url = url

    return urls
