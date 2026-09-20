from collections import defaultdict

from productos.models import Producto

from .engine import KitEngine
from .imagenes import adjuntar_imagenes_reutilizadas


def preparar_kits_gestion(kits):
    kits = list(kits)

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
            productos_por_tipo[
                producto.tipo_id
            ].append(producto)

    adjuntar_imagenes_reutilizadas(
        kits,
        productos_por_tipo=productos_por_tipo,
    )

    for kit in kits:
        productos_categoria = (
            productos_por_tipo.get(
                kit.tipo_producto_id,
                [],
            )
            if kit.modalidad == "LIBRE_CATEGORIA"
            else None
        )

        kit.opciones_gestion = (
            KitEngine.opciones(
                kit,
                productos_categoria=productos_categoria,
            )
            if kit.modalidad == "LIBRE_CATEGORIA"
            else None
        )

        # Alias temporales para mantener compatibilidad con componentes
        # internos mientras toda la gestión migra al nuevo centro.
        kit.opciones_libres_analisis = kit.opciones_gestion
        kit.recomendacion_sobre_incluidos = False
        kit.alerta_proteccion_sin_incluidos = False

        if (
            kit.modalidad == "LIBRE_CATEGORIA"
            and kit.proteger_rentabilidad_libre
            and kit.opciones_gestion
        ):
            kit.recomendacion_sobre_incluidos = bool(
                kit.opciones_gestion["cantidad_incluidos"]
            )
            kit.alerta_proteccion_sin_incluidos = (
                kit.opciones_gestion["disponible"]
                and not kit.opciones_gestion["cantidad_incluidos"]
            )

            opciones_por_producto = {
                item["producto_id"]: item
                for item in kit.opciones_gestion["opciones"]
            }
            for visual in getattr(kit, "productos_visuales", []):
                opcion = opciones_por_producto.get(
                    visual["producto"].id
                )
                if opcion:
                    visual["incluido"] = bool(opcion["incluido"])
                    visual["requiere_extra"] = bool(
                        opcion["requiere_extra"]
                    )
                    visual["extra"] = opcion["extra"]

        kit.recomendacion_gestion = (
            KitEngine.recomendacion(
                kit,
                productos_categoria=productos_categoria,
            )
        )
        kit.recomendacion_calculadora = kit.recomendacion_gestion
        kit.salud_gestion = KitEngine.estado_salud(
            kit,
            productos_categoria=productos_categoria,
        )

        kit.imagen_resumen_url = next(
            (
                visual["imagen_url"]
                for visual in getattr(
                    kit,
                    "productos_visuales",
                    [],
                )
                if visual["imagen_url"]
            ),
            "",
        )

        recomendacion = kit.recomendacion_gestion
        kit.costo_gestion = recomendacion[
            "costo_estimado"
        ]
        kit.margen_gestion = recomendacion[
            "margen_actual"
        ]

        if kit.modalidad == "FIJO":
            kit.cantidad_visible = sum(
                int(componente.cantidad or 0)
                for componente in kit.componentes.all()
            )
            kit.cantidad_opciones = len(
                list(kit.componentes.all())
            )
            kit.cantidad_premium = 0
        else:
            kit.cantidad_visible = int(
                kit.cantidad_productos or 0
            )
            analisis = kit.opciones_gestion or {}
            kit.cantidad_opciones = int(
                analisis.get(
                    "cantidad_incluidos",
                    0,
                )
                + analisis.get(
                    "cantidad_premium",
                    0,
                )
            )
            kit.cantidad_premium = int(
                analisis.get(
                    "cantidad_premium",
                    0,
                )
            )

    return kits
