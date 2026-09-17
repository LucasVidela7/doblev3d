from django.db.models import Count, Q
from django.shortcuts import render

from .image_environment import entorno_imagenes
from .imagekit_service import imagekit_configurado
from .models import Producto


def carga_masiva(request):
    """Pantalla operativa para asignar y subir muchas fotos de productos."""

    ambiente = entorno_imagenes()
    productos = list(
        Producto.objects
        .filter(solo_produccion=False)
        .select_related("tipo")
        .annotate(
            cantidad_fotos=Count(
                "imagenes",
                filter=Q(imagenes__ambiente=ambiente),
            )
        )
        .order_by("nombre", "id")
    )

    productos_json = [
        {
            "id": producto.id,
            "codigo": producto.codigo,
            "nombre": producto.nombre,
            "tipo": producto.tipo.nombre if producto.tipo_id else "",
            "fotos": int(producto.cantidad_fotos or 0),
            "activo": bool(producto.activo),
        }
        for producto in productos
    ]

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
