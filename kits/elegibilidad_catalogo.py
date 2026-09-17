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


def productos_elegibles_para_kit(kit, productos):
    """Filtra las opciones públicas de un kit libre por rentabilidad mínima."""
    if kit.modalidad == "FIJO":
        return list(productos)

    limite = costo_maximo_unitario(kit)
    if limite <= 0:
        return []

    return [
        producto
        for producto in productos
        if costo_operativo_producto(producto) <= limite
    ]


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
        elegibles = productos_elegibles_para_kit(
            kit,
            candidatos,
        )

        kit.catalogo_productos_elegibles = elegibles
        kit.catalogo_cantidad_opciones = len(elegibles)
        kit.catalogo_costo_maximo_unitario = costo_maximo_unitario(kit)

        if not elegibles:
            continue

        productos_por_kit[kit.id] = elegibles
        publicados.append(kit)

    return publicados, productos_por_kit
