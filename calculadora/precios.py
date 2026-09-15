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


def calcular_escenarios_kit_fijo(componentes):
    """Calcula un kit fijo usando exactamente la lógica de la calculadora.

    ``componentes`` es un iterable de diccionarios con ``producto`` y
    ``cantidad``. Cada producto conserva su propio margen configurado y su
    descuento por cantidad. El precio final del kit es la suma de los totales
    recomendados de sus componentes para cada escenario.
    """
    acumulados = {
        "agresivo": Decimal("0"),
        "recomendado": Decimal("0"),
        "conservador": Decimal("0"),
    }
    costo_total = Decimal("0")
    detalle = []

    for componente in componentes:
        producto = componente["producto"]
        cantidad = max(int(componente.get("cantidad") or 0), 0)

        if cantidad <= 0:
            continue

        calculo = calcular_escenarios_producto(
            producto,
            cantidad,
        )
        costo_componente = (
            calculo["costo_productivo"]
            * Decimal(cantidad)
        )
        costo_total += costo_componente

        for clave in acumulados:
            acumulados[clave] += calculo[
                "escenarios"
            ][clave]["total_recomendado"]

        detalle.append(
            {
                "producto_id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "costo_total": costo_componente,
                "escenarios": calculo["escenarios"],
            }
        )

    escenarios = {}
    for clave, total in acumulados.items():
        ganancia = total - costo_total
        margen_real = Decimal("0")

        if total > 0:
            margen_real = (
                ganancia / total * Decimal("100")
            )

        escenarios[clave] = {
            "total_recomendado": total,
            "costo_total": costo_total,
            "ganancia": ganancia,
            "margen_real": margen_real,
        }

    return {
        "costo_total": costo_total,
        "margen_piso": MARGEN_MINIMO,
        "escenarios": escenarios,
        "componentes": detalle,
    }


def _margen_real(costo, precio):
    costo = Decimal(str(costo or 0))
    precio = Decimal(str(precio or 0))
    if precio <= 0:
        return Decimal("0")
    return (precio - costo) / precio * Decimal("100")


def calcular_escenarios_kit_libre(productos, cantidad):
    """Sugiere precios para un kit libre por categoría.

    Como todavía no sabemos qué productos elegirá el cliente, se calculan dos
    referencias de costo: el promedio de la categoría y el peor caso. Cada
    producto se evalúa con la misma calculadora y con la cantidad total del kit.

    - Agresivo: promedio de los escenarios agresivos de la categoría.
    - Recomendado: promedio recomendado, pero nunca por debajo del precio
      agresivo del producto más exigente de la categoría.
    - Conservador: escenario conservador más alto de toda la categoría.

    Así el recomendado sigue siendo competitivo en una selección promedio y,
    al mismo tiempo, mantiene una protección mínima si el cliente elige la
    combinación más costosa.
    """
    cantidad = max(int(cantidad or 1), 1)
    productos = list(productos)

    if not productos:
        return {
            "cantidad": cantidad,
            "cantidad_productos_categoria": 0,
            "costo_promedio": Decimal("0"),
            "costo_peor_caso": Decimal("0"),
            "margen_piso": MARGEN_MINIMO,
            "escenarios": {},
            "productos": [],
        }

    calculos = [
        calcular_escenarios_producto(producto, cantidad)
        for producto in productos
    ]
    divisor = Decimal(len(calculos))

    costos_totales = [
        calculo["costo_productivo"] * Decimal(cantidad)
        for calculo in calculos
    ]
    costo_promedio = sum(costos_totales, Decimal("0")) / divisor
    costo_peor = max(costos_totales)

    precios_agresivos = [
        calculo["escenarios"]["agresivo"]["total_recomendado"]
        for calculo in calculos
    ]
    precios_recomendados = [
        calculo["escenarios"]["recomendado"]["total_recomendado"]
        for calculo in calculos
    ]
    precios_conservadores = [
        calculo["escenarios"]["conservador"]["total_recomendado"]
        for calculo in calculos
    ]

    agresivo = redondear_arriba(
        sum(precios_agresivos, Decimal("0")) / divisor,
        Decimal("100"),
    )
    recomendado_promedio = redondear_arriba(
        sum(precios_recomendados, Decimal("0")) / divisor,
        Decimal("100"),
    )
    recomendado = max(
        recomendado_promedio,
        max(precios_agresivos),
    )
    conservador = max(precios_conservadores)

    precios = {
        "agresivo": agresivo,
        "recomendado": recomendado,
        "conservador": conservador,
    }

    escenarios = {}
    for clave, precio in precios.items():
        escenarios[clave] = {
            "total_recomendado": precio,
            "margen_promedio": _margen_real(
                costo_promedio,
                precio,
            ),
            "margen_peor_caso": _margen_real(
                costo_peor,
                precio,
            ),
            "ganancia_promedio": precio - costo_promedio,
            "ganancia_peor_caso": precio - costo_peor,
        }

    return {
        "cantidad": cantidad,
        "cantidad_productos_categoria": len(calculos),
        "costo_promedio": costo_promedio,
        "costo_peor_caso": costo_peor,
        "margen_piso": MARGEN_MINIMO,
        "escenarios": escenarios,
        "productos": calculos,
    }
