from collections import defaultdict

from django.shortcuts import render

from productos.models import Producto

from .economia import analizar_opciones_kit, recomendacion_kit
from .imagenes import adjuntar_imagenes_reutilizadas
from .models import Kit


def lista_kits(request):
    kits = list(
        Kit.objects
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto")
        .order_by("nombre")
    )

    tipos_libres = {
        kit.tipo_producto_id
        for kit in kits
        if (
            kit.modalidad == "LIBRE_CATEGORIA"
            and kit.tipo_producto_id
        )
    }

    productos_por_tipo = defaultdict(list)
    if tipos_libres:
        productos = (
            Producto.objects
            .filter(
                tipo_id__in=tipos_libres,
                activo=True,
                solo_produccion=False,
            )
            .select_related("tipo")
            .order_by("nombre", "id")
        )
        for producto in productos:
            productos_por_tipo[producto.tipo_id].append(
                producto
            )

    adjuntar_imagenes_reutilizadas(
        kits,
        productos_por_tipo=productos_por_tipo,
    )

    for kit in kits:
        productos_categoria = None
        if kit.modalidad == "LIBRE_CATEGORIA":
            productos_categoria = productos_por_tipo.get(
                kit.tipo_producto_id,
                [],
            )

        kit.recomendacion_calculadora = recomendacion_kit(
            kit,
            productos_categoria=productos_categoria,
        )
        if kit.modalidad == "LIBRE_CATEGORIA":
            kit.opciones_libres_analisis = analizar_opciones_kit(
                kit,
                productos_categoria=productos_categoria,
            )

    return render(
        request,
        "kits/lista.html",
        {"kits": kits},
    )
