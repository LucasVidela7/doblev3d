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

        kit.recomendacion_gestion = (
            KitEngine.recomendacion(
                kit,
                productos_categoria=productos_categoria,
            )
        )
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
