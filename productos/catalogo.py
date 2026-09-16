from collections import defaultdict

from django.shortcuts import render

from kits.imagenes import adjuntar_imagenes_reutilizadas
from kits.models import Kit

from .image_environment import entorno_imagenes
from .image_models import ProductoImagen
from .models import Producto


def catalogo(request):
    """Catálogo público de productos y kits disponibles."""

    ambiente = entorno_imagenes()

    productos = list(
        Producto.objects
        .filter(
            activo=True,
            solo_produccion=False,
        )
        .select_related("tipo")
        .order_by("tipo__nombre", "nombre")
    )

    imagenes_principales = {
        imagen.producto_id: imagen
        for imagen in (
            ProductoImagen.objects
            .filter(
                producto_id__in=[producto.id for producto in productos],
                ambiente=ambiente,
                orden=1,
            )
            .order_by("producto_id", "id")
        )
    }

    productos_por_tipo = defaultdict(list)
    for producto in productos:
        producto.catalogo_imagen = imagenes_principales.get(producto.id)
        producto.catalogo_precio = producto.subtotal
        productos_por_tipo[producto.tipo_id].append(producto)

    kits = list(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto")
        .order_by("nombre")
    )
    adjuntar_imagenes_reutilizadas(
        kits,
        productos_por_tipo=productos_por_tipo,
    )

    for kit in kits:
        kit.catalogo_imagen_url = next(
            (
                visual["imagen_url"]
                for visual in kit.productos_visuales
                if visual["imagen_url"]
            ),
            "",
        )

    categorias = sorted(
        {
            producto.tipo.nombre
            for producto in productos
            if producto.tipo_id and producto.tipo
        }
    )

    return render(
        request,
        "productos/catalogo_publico.html",
        {
            "productos": productos,
            "kits": kits,
            "categorias": categorias,
            "ambiente_catalogo": ambiente,
            "es_ambiente_no_productivo": ambiente != "production",
        },
    )
