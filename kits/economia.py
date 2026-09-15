from decimal import Decimal

from calculadora.precios import (
    MARGEN_MINIMO,
    calcular_escenarios_kit_fijo,
    calcular_escenarios_kit_libre,
)
from productos.models import Producto


ESCENARIOS = (
    "agresivo",
    "recomendado",
    "conservador",
)


def _decimal(valor):
    return Decimal(str(valor or 0))


def _margen(costo, precio):
    costo = _decimal(costo)
    precio = _decimal(precio)
    if precio <= 0:
        return None
    return (
        (precio - costo)
        / precio
        * Decimal("100")
    ).quantize(Decimal("0.1"))


def _componentes_fijos(kit):
    cache = getattr(
        kit,
        "_prefetched_objects_cache",
        {},
    )

    if "componentes" in cache:
        componentes = list(cache["componentes"])
    else:
        componentes = list(
            kit.componentes
            .select_related("producto")
            .all()
        )

    return [
        {
            "producto": componente.producto,
            "cantidad": componente.cantidad,
        }
        for componente in componentes
        if componente.cantidad > 0
    ]


def _productos_categoria(kit):
    if not kit.tipo_producto_id:
        return []

    return list(
        Producto.objects
        .filter(
            tipo_id=kit.tipo_producto_id,
            activo=True,
            solo_produccion=False,
        )
        .order_by("id")
    )


def recomendacion_kit(kit, productos_categoria=None):
    """Devuelve la recomendación comercial vigente para un kit.

    Usa exactamente los escenarios de la calculadora. El estado del precio
    actual se interpreta así:

    - REVISAR: por debajo de Agresivo.
    - ADVERTENCIA: entre Agresivo y Recomendado.
    - OK: Recomendado o superior.

    Conservador se muestra como referencia de mayor protección, pero no se
    exige para considerar el precio saludable.
    """
    precio_actual = _decimal(kit.precio)

    resultado = {
        "disponible": False,
        "tipo_calculo": (
            "EXACTO"
            if kit.modalidad == "FIJO"
            else "ESTIMADO"
        ),
        "precio_actual": precio_actual,
        "precio_agresivo": Decimal("0"),
        "precio_recomendado": Decimal("0"),
        "precio_conservador": Decimal("0"),
        "costo_estimado": Decimal("0"),
        "costo_peor_caso": Decimal("0"),
        "margen_actual": None,
        "margen_peor_caso": None,
        "margen_piso": MARGEN_MINIMO,
        "estado": "SIN_DATOS",
        "alerta": True,
        "critico": False,
        "motivo": "",
        "escenarios": {},
    }

    if kit.modalidad == "FIJO":
        componentes = _componentes_fijos(kit)
        if not componentes:
            resultado["motivo"] = (
                "El kit no tiene componentes configurados."
            )
            return resultado

        calculo = calcular_escenarios_kit_fijo(
            componentes
        )
        costo = _decimal(calculo["costo_total"])

        if costo <= 0:
            resultado["motivo"] = (
                "Los componentes no tienen un costo productivo calculable."
            )
            return resultado

        resultado["costo_estimado"] = costo
        resultado["costo_peor_caso"] = costo
        resultado["margen_actual"] = _margen(
            costo,
            precio_actual,
        )
        resultado["margen_peor_caso"] = (
            resultado["margen_actual"]
        )

        for clave in ESCENARIOS:
            escenario = calculo["escenarios"][clave]
            resultado["escenarios"][clave] = {
                "precio": _decimal(
                    escenario["total_recomendado"]
                ),
                "margen": _decimal(
                    escenario["margen_real"]
                ).quantize(Decimal("0.1")),
                "margen_peor_caso": _decimal(
                    escenario["margen_real"]
                ).quantize(Decimal("0.1")),
            }

    else:
        if (
            not kit.tipo_producto_id
            or int(kit.cantidad_productos or 0) <= 0
        ):
            resultado["motivo"] = (
                "El kit libre no tiene categoría o cantidad válida."
            )
            return resultado

        productos = (
            list(productos_categoria)
            if productos_categoria is not None
            else _productos_categoria(kit)
        )

        if not productos:
            resultado["motivo"] = (
                "No hay productos comerciales activos en la categoría."
            )
            return resultado

        calculo = calcular_escenarios_kit_libre(
            productos,
            kit.cantidad_productos,
        )

        costo_promedio = _decimal(
            calculo["costo_promedio"]
        )
        costo_peor = _decimal(
            calculo["costo_peor_caso"]
        )

        if costo_peor <= 0:
            resultado["motivo"] = (
                "La categoría no tiene costos productivos calculables."
            )
            return resultado

        resultado["costo_estimado"] = costo_promedio
        resultado["costo_peor_caso"] = costo_peor
        resultado["margen_actual"] = _margen(
            costo_promedio,
            precio_actual,
        )
        resultado["margen_peor_caso"] = _margen(
            costo_peor,
            precio_actual,
        )

        for clave in ESCENARIOS:
            escenario = calculo["escenarios"][clave]
            resultado["escenarios"][clave] = {
                "precio": _decimal(
                    escenario["total_recomendado"]
                ),
                "margen": _decimal(
                    escenario["margen_promedio"]
                ).quantize(Decimal("0.1")),
                "margen_peor_caso": _decimal(
                    escenario["margen_peor_caso"]
                ).quantize(Decimal("0.1")),
            }

    resultado["disponible"] = True
    resultado["precio_agresivo"] = resultado[
        "escenarios"
    ]["agresivo"]["precio"]
    resultado["precio_recomendado"] = resultado[
        "escenarios"
    ]["recomendado"]["precio"]
    resultado["precio_conservador"] = resultado[
        "escenarios"
    ]["conservador"]["precio"]

    if precio_actual <= 0:
        resultado["estado"] = "REVISAR"
        resultado["critico"] = True
        resultado["motivo"] = (
            "El kit no tiene un precio de venta válido."
        )
    elif precio_actual < resultado["precio_agresivo"]:
        resultado["estado"] = "REVISAR"
        resultado["critico"] = True
        resultado["motivo"] = (
            "El precio actual está por debajo incluso del escenario "
            "Agresivo de la calculadora."
        )
    elif precio_actual < resultado["precio_recomendado"]:
        resultado["estado"] = "ADVERTENCIA"
        resultado["motivo"] = (
            "El precio actual supera Agresivo, pero todavía está por "
            "debajo del precio Recomendado."
        )
    else:
        resultado["estado"] = "OK"
        resultado["alerta"] = False
        resultado["motivo"] = (
            "El precio actual está dentro o por encima del escenario "
            "Recomendado."
        )

    return resultado
