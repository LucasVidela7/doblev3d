from collections import defaultdict

from productos.image_environment import (
    ambientes_imagenes_lectura,
    clave_imagen_lectura,
)
from productos.image_models import ProductoImagen


MAX_VISIBLES_LISTADO = 8
MAX_FOTOS_COLLAGE = 4


def adjuntar_imagenes_reutilizadas(kits, productos_por_tipo=None):
    """Adjunta a cada kit las fotos principales de sus productos.

    No crea relaciones ni archivos nuevos: sólo reutiliza la foto principal del
    producto correspondiente al ambiente actual.
    """
    productos_por_tipo = productos_por_tipo or defaultdict(list)
    kits = list(kits)

    ids_productos = set()
    for kit in kits:
        if kit.modalidad == "FIJO":
            ids_productos.update(
                componente.producto_id
                for componente in kit.componentes.all()
            )
        elif kit.tipo_producto_id:
            productos_libres = getattr(
                kit,
                "catalogo_productos_visuales",
                productos_por_tipo.get(kit.tipo_producto_id, []),
            )
            ids_productos.update(
                producto.id
                for producto in productos_libres
            )

    imagenes_principales = {}
    candidatas = list(
        ProductoImagen.objects
        .filter(
            producto_id__in=ids_productos,
            ambiente__in=ambientes_imagenes_lectura(),
            orden=1,
        )
        .order_by("producto_id", "id")
    )
    candidatas.sort(
        key=lambda imagen: (
            imagen.producto_id,
            *clave_imagen_lectura(imagen),
        )
    )
    for imagen in candidatas:
        imagenes_principales.setdefault(imagen.producto_id, imagen)

    for kit in kits:
        visuales = []

        if kit.modalidad == "FIJO":
            for componente in kit.componentes.all():
                imagen = imagenes_principales.get(componente.producto_id)
                visuales.append(
                    {
                        "producto": componente.producto,
                        "cantidad": componente.cantidad,
                        "imagen": imagen,
                        # En el catálogo/listados visuales grandes usamos la
                        # imagen original. El thumbnail de ImageKit está pensado
                        # para previews pequeñas y pierde definición al ocupar
                        # una tarjeta 1:1 de mayor tamaño.
                        "imagen_url": imagen.url if imagen else "",
                    }
                )
        else:
            productos_libres = getattr(
                kit,
                "catalogo_productos_visuales",
                productos_por_tipo.get(kit.tipo_producto_id, []),
            )
            for producto in productos_libres:
                imagen = imagenes_principales.get(producto.id)
                visuales.append(
                    {
                        "producto": producto,
                        "cantidad": None,
                        "imagen": imagen,
                        "imagen_url": imagen.url if imagen else "",
                    }
                )

        # El detalle del kit conserva todos los productos. Para el collage del
        # catálogo usamos exclusivamente productos con foto, así nunca ocupamos
        # un espacio con una letra si existe una imagen real disponible.
        fotos_collage = [
            visual
            for visual in visuales
            if visual["imagen_url"]
        ][:MAX_FOTOS_COLLAGE]

        kit.productos_visuales = visuales
        kit.productos_visuales_visibles = visuales[:MAX_VISIBLES_LISTADO]
        kit.productos_visuales_extra = max(
            len(visuales) - MAX_VISIBLES_LISTADO,
            0,
        )
        kit.productos_visuales_collage = fotos_collage

    return kits
