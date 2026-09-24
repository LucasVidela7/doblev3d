from .image_environment import (
    ambientes_imagenes_lectura,
    clave_imagen_lectura,
)
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

    imagenes = list(
        ProductoImagen.objects
        .filter(
            producto_id__in=productos_por_id.keys(),
            ambiente__in=ambientes_imagenes_lectura(),
            orden=1,
        )
        .only(
            "id",
            "producto_id",
            "ambiente",
            "orden",
            "thumbnail_url",
            "url",
        )
    )
    imagenes.sort(
        key=lambda imagen: (
            imagen.producto_id,
            *clave_imagen_lectura(imagen),
        )
    )

    urls = {}
    for imagen in imagenes:
        urls.setdefault(
            imagen.producto_id,
            imagen.thumbnail_url or imagen.url or "",
        )

    for producto_id, instancias in productos_por_id.items():
        url = urls.get(producto_id, "")
        for producto in instancias:
            producto.imagen_produccion_url = url

    return urls
