from decimal import Decimal

from productos.models import provision_empaque_unitaria_actual

from calculadora.precios import (
    MARGEN_MINIMO,
    calcular_escenarios_producto,
    margen_sugerido,
    margenes_escenario,
    precio_mayorista,
    redondear_arriba,
)


ESCENARIOS = (
    "agresivo",
    "recomendado",
    "conservador",
)


def _decimal(valor):
    return Decimal(str(valor or 0))


def _margen_real(costo, precio):
    costo = _decimal(costo)
    precio = _decimal(precio)
    if precio <= 0:
        return Decimal("0")
    return (precio - costo) / precio * Decimal("100")


def calcular_escenarios_kit_fijo(componentes):
    """Calcula un kit fijo como una única compra por volumen.

    Cada componente conserva su costo productivo real y se valoriza con el
    filamento para cantidad. A diferencia de la lógica anterior, los precios
    sugeridos no se obtienen sumando la recomendación de cada bloque por
    separado: primero se suma el costo de toda la composición y luego se aplica
    la curva de margen sobre la cantidad TOTAL de piezas del kit.

    El margen base del kit es el promedio de los márgenes configurados de sus
    productos, ponderado por el costo productivo que cada componente aporta al
    kit. De esta manera un componente pequeño no distorsiona el margen de toda
    la composición.
    """
    costo_total = Decimal("0")
    cantidad_total = 0
    margen_ponderado = Decimal("0")
    detalle = []
    precio_filamento_kg = Decimal("0")
    filamento_economico = False
    referencia_separada = {
        clave: Decimal("0")
        for clave in ESCENARIOS
    }

    for componente in componentes:
        producto = componente["producto"]
        cantidad = max(int(componente.get("cantidad") or 0), 0)

        if cantidad <= 0:
            continue

        calculo = calcular_escenarios_producto(
            producto,
            cantidad,
            forzar_filamento_economico=True,
            incluir_provision_empaque=False,
        )
        costo_unitario = _decimal(calculo["costo_productivo"])
        costo_componente = costo_unitario * Decimal(cantidad)
        margen_producto = max(
            _decimal(producto.margen_ganancia),
            MARGEN_MINIMO,
        )

        costo_total += costo_componente
        cantidad_total += cantidad
        margen_ponderado += margen_producto * costo_componente

        if calculo["precio_filamento_kg"] > 0:
            precio_filamento_kg = _decimal(
                calculo["precio_filamento_kg"]
            )
        filamento_economico = (
            filamento_economico
            or bool(calculo["filamento_economico"])
        )

        for clave in ESCENARIOS:
            referencia_separada[clave] += _decimal(
                calculo["escenarios"][clave]["total_recomendado"]
            )

        detalle.append(
            {
                "producto_id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "costo_unitario": costo_unitario,
                "costo_total": costo_componente,
                "margen_tope": margen_producto,
                "precio_filamento_kg": _decimal(
                    calculo["precio_filamento_kg"]
                ),
                "filamento_economico": bool(
                    calculo["filamento_economico"]
                ),
                "escenarios_separados": calculo["escenarios"],
            }
        )

    costo_componentes = costo_total
    provision_empaque = provision_empaque_unitaria_actual()
    costo_total += provision_empaque

    if cantidad_total <= 0:
        return {
            "cantidad_total": 0,
            "costo_total": provision_empaque,
            "provision_empaque": provision_empaque,
            "margen_tope_ponderado": MARGEN_MINIMO,
            "margen_piso": MARGEN_MINIMO,
            "precio_filamento_kg": Decimal("0"),
            "filamento_economico": False,
            "tipo_filamento": "estandar",
            "escenarios": {},
            "componentes": [],
        }

    margen_tope_ponderado = MARGEN_MINIMO
    if costo_componentes > 0:
        margen_tope_ponderado = max(
            margen_ponderado / costo_componentes,
            MARGEN_MINIMO,
        )

    margenes = margenes_escenario(
        cantidad_total,
        margen_tope_ponderado,
    )

    escenarios = {}
    for clave in ESCENARIOS:
        margen_objetivo = margenes[clave]
        total_sin_redondear = precio_mayorista(
            costo_total,
            margen_objetivo,
        )
        total_recomendado = redondear_arriba(
            total_sin_redondear,
            Decimal("100"),
        )
        ganancia = total_recomendado - costo_total
        referencia = referencia_separada[clave]

        escenarios[clave] = {
            "cantidad_total": cantidad_total,
            "margen_objetivo": margen_objetivo,
            "total_sin_redondear": total_sin_redondear,
            "total_recomendado": total_recomendado,
            "precio_promedio_pieza": (
                total_recomendado / Decimal(cantidad_total)
            ).quantize(Decimal("0.01")),
            "costo_total": costo_total,
            "ganancia": ganancia,
            "margen_real": _margen_real(
                costo_total,
                total_recomendado,
            ),
            "referencia_separada": referencia,
            "ahorro_combo": max(
                referencia - total_recomendado,
                Decimal("0"),
            ),
        }

    return {
        "cantidad_total": cantidad_total,
        "costo_total": costo_total,
        "provision_empaque": provision_empaque,
        "margen_tope_ponderado": margen_tope_ponderado,
        "margen_recomendado": margen_sugerido(
            cantidad_total,
            margen_tope_ponderado,
        ),
        "margen_piso": MARGEN_MINIMO,
        "precio_filamento_kg": precio_filamento_kg,
        "filamento_economico": filamento_economico,
        "tipo_filamento": (
            "cantidad"
            if filamento_economico
            else "estandar"
        ),
        "escenarios": escenarios,
        "componentes": detalle,
    }
