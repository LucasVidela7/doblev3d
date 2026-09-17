from collections import defaultdict

from django.shortcuts import render

from .image_environment import entorno_imagenes
from .image_models import ProductoImagen
from .imagekit_service import imagekit_configurado
from .models import Producto


def carga_masiva(request):
    """Pantalla operativa para asignar, agregar y reemplazar fotos en lote."""

    ambiente = entorno_imagenes()
    productos = list(
        Producto.objects
        .filter(solo_produccion=False)
        .select_related("tipo")
        .order_by("nombre", "id")
    )

    imagenes_por_producto = defaultdict(list)
    for imagen in (
        ProductoImagen.objects
        .filter(
            producto_id__in=[producto.id for producto in productos],
            ambiente=ambiente,
        )
        .order_by("producto_id", "orden", "id")
    ):
        imagenes_por_producto[imagen.producto_id].append(imagen)

    productos_json = []
    for producto in productos:
        imagenes = imagenes_por_producto.get(producto.id, [])
        productos_json.append(
            {
                "id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
                "tipo": producto.tipo.nombre if producto.tipo_id else "",
                "fotos": len(imagenes),
                "activo": bool(producto.activo),
                "imagenes": [
                    {
                        "id": imagen.id,
                        "orden": imagen.orden,
                        "principal": imagen.orden == 1,
                        "preview_url": imagen.thumbnail_url or imagen.url,
                        "url": imagen.url,
                    }
                    for imagen in imagenes
                ],
            }
        )

    return render(
        request,
        "productos/imagenes_masivas.html",
        {
            "productos_carga": productos,
            "productos_json": productos_json,
            "imagekit_configurado": imagekit_configurado(),
            "ambiente_imagenes": ambiente,
        },
    )
