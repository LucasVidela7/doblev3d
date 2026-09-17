from collections import defaultdict

from django.shortcuts import render

from productos.models import Producto

from .economia import recomendacion_kit
from .elegibilidad_catalogo import resumen_elegibilidad_kit
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

    productos_por_kit = {}
    for kit in kits:
        if kit.modalidad != "LIBRE_CATEGORIA":
            continue

        resumen = resumen_elegibilidad_kit(
            kit,
            productos_por_tipo.get(
                kit.tipo_producto_id,
                [],
            ),
        )
        kit.catalogo_cantidad_opciones = resumen["cantidad"]
        kit.catalogo_cantidad_excluida = resumen["cantidad_excluida"]
        kit.catalogo_costo_maximo_unitario = resumen[
            "costo_maximo_unitario"
        ]
        productos_por_kit[kit.id] = resumen["productos"]

    adjuntar_imagenes_reutilizadas(
        kits,
        productos_por_tipo=productos_por_tipo,
        productos_por_kit=productos_por_kit,
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

    return render(
        request,
        "kits/lista.html",
        {"kits": kits},
    )
