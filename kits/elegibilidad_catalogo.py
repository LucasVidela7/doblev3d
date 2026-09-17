from decimal import Decimal

from .models import MARGEN_MINIMO_KIT


def _decimal(valor):
    return Decimal(str(valor or 0))


def costo_operativo_producto(producto):
    """Costo real usado para decidir si un producto entra en un kit libre."""
    costo = _decimal(producto.costo)
    seguro = _decimal(producto.seguro)
    return max(costo + seguro, Decimal("0"))


def costo_maximo_unitario(kit, margen_minimo=MARGEN_MINIMO_KIT):
    """Máximo costo por unidad para que cualquier combinación conserve margen."""
    precio = _decimal(kit.precio)
    cantidad = int(kit.cantidad_productos or 0)
    margen = _decimal(margen_minimo)

    if precio <= 0 or cantidad <= 0:
        return Decimal("0")

    proporcion_costo = Decimal("1") - (margen / Decimal("100"))
    if proporcion_costo <= 0:
        return Decimal("0")

    return (
        precio
        * proporcion_costo
        / Decimal(cantidad)
    )


def producto_es_elegible_para_kit(
    kit,
    producto,
    margen_minimo=MARGEN_MINIMO_KIT,
):
    """Regla única de rentabilidad para kits libres en catálogo y Gestión."""
    if kit.modalidad == "FIJO":
        return True

    if (
        not kit.tipo_producto_id
        or not getattr(producto, "activo", False)
        or getattr(producto, "solo_produccion", False)
        or producto.tipo_id != kit.tipo_producto_id
    ):
        return False

    limite = costo_maximo_unitario(
        kit,
        margen_minimo=margen_minimo,
    )
    if limite <= 0:
        return False

    return costo_operativo_producto(producto) <= limite


def productos_elegibles_para_kit(
    kit,
    productos,
    margen_minimo=MARGEN_MINIMO_KIT,
):
    """Filtra opciones comerciales de un kit libre por rentabilidad mínima."""
    if kit.modalidad == "FIJO":
        return list(productos)

    return [
        producto
        for producto in productos
        if producto_es_elegible_para_kit(
            kit,
            producto,
            margen_minimo=margen_minimo,
        )
    ]


def resumen_elegibilidad_kit(kit, productos):
    """Adjunta datos útiles para UI sin exponer costos en el catálogo público."""
    candidatos = list(productos)
    elegibles = productos_elegibles_para_kit(
        kit,
        candidatos,
    )
    return {
        "productos": elegibles,
        "cantidad": len(elegibles),
        "cantidad_excluida": max(len(candidatos) - len(elegibles), 0),
        "costo_maximo_unitario": costo_maximo_unitario(kit),
        "margen_minimo": MARGEN_MINIMO_KIT,
    }


def preparar_kits_catalogo(kits, productos_por_tipo):
    """Adjunta opciones rentables y oculta kits libres sin ninguna opción."""
    publicados = []
    productos_por_kit = {}

    for kit in kits:
        if kit.modalidad == "FIJO":
            publicados.append(kit)
            continue

        candidatos = productos_por_tipo.get(
            kit.tipo_producto_id,
            [],
        )
        resumen = resumen_elegibilidad_kit(
            kit,
            candidatos,
        )
        elegibles = resumen["productos"]

        kit.catalogo_productos_elegibles = elegibles
        kit.catalogo_cantidad_opciones = resumen["cantidad"]
        kit.catalogo_costo_maximo_unitario = resumen[
            "costo_maximo_unitario"
        ]

        if not elegibles:
            continue

        productos_por_kit[kit.id] = elegibles
        publicados.append(kit)

    return publicados, productos_por_kit
