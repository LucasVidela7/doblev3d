from collections import defaultdict

from productos.image_environment import entorno_imagenes
from productos.image_models import ProductoImagen


MAX_VISIBLES_LISTADO = 8


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
            ids_productos.update(
                producto.id
                for producto in productos_por_tipo.get(kit.tipo_producto_id, [])
            )

    imagenes_principales = {
        imagen.producto_id: imagen
        for imagen in (
            ProductoImagen.objects
            .filter(
                producto_id__in=ids_productos,
                ambiente=entorno_imagenes(),
                orden=1,
            )
            .order_by("producto_id", "id")
        )
    }

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
                        "imagen_url": (
                            (imagen.thumbnail_url or imagen.url)
                            if imagen
                            else ""
                        ),
                    }
                )
        else:
            for producto in productos_por_tipo.get(kit.tipo_producto_id, []):
                imagen = imagenes_principales.get(producto.id)
                visuales.append(
                    {
                        "producto": producto,
                        "cantidad": None,
                        "imagen": imagen,
                        "imagen_url": (
                            (imagen.thumbnail_url or imagen.url)
                            if imagen
                            else ""
                        ),
                    }
                )

        kit.productos_visuales = visuales
        kit.productos_visuales_visibles = visuales[:MAX_VISIBLES_LISTADO]
        kit.productos_visuales_extra = max(
            len(visuales) - MAX_VISIBLES_LISTADO,
            0,
        )

    return kits
