from decimal import Decimal, ROUND_CEILING
from math import log10

MARGEN_MINIMO = Decimal("22.5")
CANTIDAD_PISO_MARGEN = Decimal("1500")
DIFERENCIA_ESCENARIO = Decimal("4")


def redondear_arriba(valor, multiplo=Decimal("100")):
    valor = Decimal(valor)
    multiplo = Decimal(multiplo)
    if valor <= 0:
        return Decimal("0")
    return (
        (valor / multiplo).to_integral_value(rounding=ROUND_CEILING)
        * multiplo
    )


def margen_sugerido(cantidad, margen_tope):
    cantidad = max(int(cantidad or 1), 1)
    margen_tope = max(Decimal(str(margen_tope)), MARGEN_MINIMO)

    if cantidad <= 1:
        return margen_tope.quantize(Decimal("0.1"))

    if Decimal(cantidad) >= CANTIDAD_PISO_MARGEN:
        return MARGEN_MINIMO

    progreso = (
        Decimal(str(log10(cantidad)))
        / Decimal(str(log10(float(CANTIDAD_PISO_MARGEN))))
    )

    margen = (
        margen_tope
        - (margen_tope - MARGEN_MINIMO) * progreso
    )

    return max(
        min(margen, margen_tope),
        MARGEN_MINIMO,
    ).quantize(Decimal("0.1"))


def precio_mayorista(costo_productivo, margen):
    costo_productivo = Decimal(str(costo_productivo))
    margen = Decimal(str(margen))

    if costo_productivo <= 0 or margen >= Decimal("100"):
        return Decimal("0")

    factor = Decimal("1") - margen / Decimal("100")
    if factor <= 0:
        return Decimal("0")

    return (
        costo_productivo / factor
    ).quantize(Decimal("0.01"))


def fila_precio(costo_productivo, cantidad, margen=None, margen_tope=Decimal("60")):
    cantidad = max(int(cantidad or 1), 1)
    costo_productivo = Decimal(str(costo_productivo))

    margen_objetivo = (
        Decimal(str(margen))
        if margen is not None
        else margen_sugerido(cantidad, margen_tope)
    )

    precio_unitario = precio_mayorista(
        costo_productivo,
        margen_objetivo,
    )

    total_sin_redondear = precio_unitario * Decimal(cantidad)
    total_recomendado = redondear_arriba(
        total_sin_redondear,
        Decimal("100"),
    )

    precio_unitario_pedido = (
        total_recomendado / Decimal(cantidad)
    ).quantize(Decimal("0.01"))

    total_pedido = (
        precio_unitario_pedido * Decimal(cantidad)
    )

    costo_total = costo_productivo * Decimal(cantidad)
    ganancia = total_pedido - costo_total

    margen_real = Decimal("0")
    if total_pedido > 0:
        margen_real = ganancia / total_pedido * Decimal("100")

    return {
        "cantidad": cantidad,
        "margen_objetivo": margen_objetivo,
        "precio_unitario": precio_unitario,
        "total_sin_redondear": total_sin_redondear,
        "total_recomendado": total_recomendado,
        "precio_unitario_pedido": precio_unitario_pedido,
        "total_pedido": total_pedido,
        "costo_total": costo_total,
        "ganancia": ganancia,
        "margen_real": margen_real,
    }


def margenes_escenario(cantidad, margen_tope):
    margen_tope = max(Decimal(str(margen_tope)), MARGEN_MINIMO)
    recomendado = margen_sugerido(cantidad, margen_tope)

    return {
        "conservador": min(
            recomendado + DIFERENCIA_ESCENARIO,
            margen_tope,
        ),
        "recomendado": recomendado,
        "agresivo": max(
            recomendado - DIFERENCIA_ESCENARIO,
            MARGEN_MINIMO,
        ),
    }


def calcular_escenarios_producto(producto, cantidad):
    cantidad = max(int(cantidad or 1), 1)

    costo_productivo = (
        Decimal(str(producto.costo))
        + Decimal(str(producto.seguro))
    )

    margen_tope = max(
        Decimal(str(producto.margen_ganancia)),
        MARGEN_MINIMO,
    )

    margenes = margenes_escenario(cantidad, margen_tope)
    escenarios = {
        clave: fila_precio(
            costo_productivo,
            cantidad,
            margen=margen,
            margen_tope=margen_tope,
        )
        for clave, margen in margenes.items()
    }

    return {
        "producto_id": producto.id,
        "codigo": producto.codigo,
        "nombre": producto.nombre,
        "cantidad": cantidad,
        "precio_lista": Decimal(str(producto.subtotal)),
        "costo_productivo": costo_productivo,
        "margen_tope": margen_tope,
        "margen_piso": MARGEN_MINIMO,
        "escenarios": escenarios,
    }
