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
        productos_referencia = None

        kit.recomendacion_sobre_incluidos = False
        kit.alerta_proteccion_sin_incluidos = False

        if kit.modalidad == "LIBRE_CATEGORIA":
            productos_categoria = productos_por_tipo.get(
                kit.tipo_producto_id,
                [],
            )
            kit.opciones_libres_analisis = analizar_opciones_kit(
                kit,
                productos_categoria=productos_categoria,
            )

            productos_referencia = productos_categoria

            if kit.proteger_rentabilidad_libre:
                incluidos = [
                    item["producto"]
                    for item in kit.opciones_libres_analisis["incluidos"]
                ]

                if incluidos:
                    productos_referencia = incluidos
                    kit.recomendacion_sobre_incluidos = True
                elif kit.opciones_libres_analisis["disponible"]:
                    kit.alerta_proteccion_sin_incluidos = True

            opciones_por_producto = {
                item["producto_id"]: item
                for item in kit.opciones_libres_analisis["opciones"]
            }
            for visual in getattr(kit, "productos_visuales", []):
                opcion = opciones_por_producto.get(
                    visual["producto"].id
                )
                if not opcion:
                    continue

                visual["incluido"] = bool(opcion["incluido"])
                visual["requiere_extra"] = bool(
                    opcion["requiere_extra"]
                )
                visual["extra"] = opcion["extra"]
                visual["extra_sugerido"] = opcion[
                    "extra_sugerido"
                ]
                visual["protegido"] = bool(
                    kit.proteger_rentabilidad_libre
                )

        kit.recomendacion_calculadora = recomendacion_kit(
            kit,
            productos_categoria=productos_referencia,
        )

    return render(
        request,
        "kits/lista.html",
        {"kits": kits},
    )
