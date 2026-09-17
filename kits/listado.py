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
        kit.catalogo_cantidad_premium = resumen["cantidad_premium"]
        kit.catalogo_cantidad_total = resumen["cantidad_total"]
        kit.catalogo_cantidad_excluida = resumen["cantidad_excluida"]
        kit.catalogo_costo_maximo_unitario = resumen[
            "costo_maximo_unitario"
        ]
        kit.catalogo_adicional_minimo = resumen["adicional_minimo"]
        kit.catalogo_adicional_maximo = resumen["adicional_maximo"]
        kit.catalogo_margen_promedio_efectivo = resumen[
            "margen_promedio_efectivo"
        ]
        kit.catalogo_margen_peor_efectivo = resumen[
            "margen_peor_efectivo"
        ]
        kit.catalogo_opciones = resumen["opciones"]
        productos_por_kit[kit.id] = [
            opcion["producto"]
            for opcion in resumen["opciones"]
        ]

    adjuntar_imagenes_reutilizadas(
        kits,
        productos_por_tipo=productos_por_tipo,
        productos_por_kit=productos_por_kit,
    )

    for kit in kits:
        productos_categoria = None
        if kit.modalidad == "LIBRE_CATEGORIA":
            # Las referencias del precio base se calculan sólo con las opciones
            # incluidas sin adicional. Las premium tienen su propio recargo.
            productos_categoria = [
                opcion["producto"]
                for opcion in getattr(
                    kit,
                    "catalogo_opciones",
                    [],
                )
                if opcion["incluido"]
            ]

        kit.recomendacion_calculadora = recomendacion_kit(
            kit,
            productos_categoria=productos_categoria,
        )

    return render(
        request,
        "kits/lista.html",
        {"kits": kits},
    )
