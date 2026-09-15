from decimal import Decimal, ROUND_CEILING
from math import log10

MARGEN_MINIMO = Decimal("22.5")
CANTIDAD_PISO_MARGEN = Decimal("1500")
DIFERENCIA_ESCENARIO = Decimal("4")


def _decimal(valor, default=Decimal("0")):
    try:
        if valor in (None, ""):
            return default
        return Decimal(str(valor))
    except Exception:
        return default


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


def desglose_productivo(producto, cantidad=1, precio_filamento_kg=None):
    """
    Desglose de costo unitario para una venta de ``cantidad`` unidades.

    El producto y su precio de lista siguen usando siempre el coste estándar.
    Este cálculo es exclusivo de la calculadora de cantidades/kits y puede
    elegir un precio de filamento más económico según los gramos totales.
    """
    cantidad = max(int(cantidad or 1), 1)
    peso_unitario = max(
        _decimal(getattr(producto, "peso_gramos", 0)),
        Decimal("0"),
    )
    peso_total = peso_unitario * Decimal(cantidad)

    config = producto.obtener_configuracion()

    vacio = {
        "config": config,
        "cantidad": cantidad,
        "peso_unitario_gramos": peso_unitario,
        "peso_total_gramos": peso_total,
        "horas_totales": Decimal("0"),
        "costo_luz": Decimal("0"),
        "costo_material": Decimal("0"),
        "amortizacion": Decimal("0"),
        "provision_fallos": Decimal("0"),
        "costo": Decimal("0"),
        "seguro": Decimal("0"),
        "costo_productivo": Decimal("0"),
        "costo_productivo_total": Decimal("0"),
        "precio_filamento_estandar_kg": Decimal("0"),
        "precio_filamento_kg": Decimal("0"),
        "tramo_desde_gramos": None,
        "usa_filamento_volumen": False,
    }

    if not config or not getattr(producto, "requiere_impresion", True):
        return vacio

    estandar = max(
        _decimal(config.coste_plastico_kg),
        Decimal("0"),
    )
    tramo = None

    if precio_filamento_kg is None:
        tramo = config.tramo_filamento_para_gramos(peso_total)
        precio_filamento_kg = config.precio_filamento_para_gramos(peso_total)
    else:
        precio_filamento_kg = max(
            _decimal(precio_filamento_kg),
            Decimal("0"),
        )
        if estandar > 0:
            precio_filamento_kg = min(
                estandar,
                precio_filamento_kg,
            )

    horas_totales = max(
        _decimal(producto.horas_totales),
        Decimal("0"),
    )
    costo_luz = horas_totales * _decimal(config.coste_luz_hora)
    costo_material = (
        peso_unitario
        * precio_filamento_kg
        / Decimal("1000")
    )
    costo = costo_luz + costo_material
    amortizacion = (
        horas_totales
        * _decimal(config.coste_amortizacion_hora)
    )
    tasa_fallos = _decimal(config.tasa_fallos) / Decimal("100")
    provision_fallos = (amortizacion + costo) * tasa_fallos
    seguro = amortizacion + provision_fallos
    costo_productivo = costo + seguro

    return {
        "config": config,
        "cantidad": cantidad,
        "peso_unitario_gramos": peso_unitario,
        "peso_total_gramos": peso_total,
        "horas_totales": horas_totales,
        "costo_luz": costo_luz,
        "costo_material": costo_material,
        "amortizacion": amortizacion,
        "provision_fallos": provision_fallos,
        "costo": costo,
        "seguro": seguro,
        "costo_productivo": costo_productivo,
        "costo_productivo_total": (
            costo_productivo * Decimal(cantidad)
        ),
        "precio_filamento_estandar_kg": estandar,
        "precio_filamento_kg": precio_filamento_kg,
        "tramo_desde_gramos": (
            _decimal(tramo.desde_gramos)
            if tramo is not None
            else None
        ),
        "usa_filamento_volumen": (
            precio_filamento_kg < estandar
            if estandar > 0
            else False
        ),
    }


def calcular_escenarios_producto(
    producto,
    cantidad,
    precio_filamento_kg=None,
):
    cantidad = max(int(cantidad or 1), 1)
    desglose = desglose_productivo(
        producto,
        cantidad,
        precio_filamento_kg=precio_filamento_kg,
    )
    costo_productivo = desglose["costo_productivo"]

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
        "costo_productivo_total": desglose["costo_productivo_total"],
        "peso_total_gramos": desglose["peso_total_gramos"],
        "precio_filamento_estandar_kg": desglose[
            "precio_filamento_estandar_kg"
        ],
        "precio_filamento_kg": desglose["precio_filamento_kg"],
        "tramo_desde_gramos": desglose["tramo_desde_gramos"],
        "usa_filamento_volumen": desglose["usa_filamento_volumen"],
        "desglose": desglose,
        "margen_tope": margen_tope,
        "margen_piso": MARGEN_MINIMO,
        "escenarios": escenarios,
    }


def calcular_escenarios_kit_fijo(componentes):
    """
    Calcula un kit fijo con la misma lógica de la calculadora.

    El precio de filamento por volumen se decide con el peso TOTAL de toda la
    composición del kit. Después ese mismo precio/kg se aplica a cada
    componente, evitando que varios componentes chicos pierdan el beneficio
    por evaluarse por separado.
    """
    componentes = [
        componente
        for componente in componentes
        if max(int(componente.get("cantidad") or 0), 0) > 0
    ]

    acumulados = {
        "agresivo": Decimal("0"),
        "recomendado": Decimal("0"),
        "conservador": Decimal("0"),
    }
    costo_total = Decimal("0")
    detalle = []
    peso_total_gramos = sum(
        (
            max(
                _decimal(getattr(item["producto"], "peso_gramos", 0)),
                Decimal("0"),
            )
            * Decimal(max(int(item.get("cantidad") or 0), 0))
        )
        for item in componentes
    ) if componentes else Decimal("0")

    config = (
        componentes[0]["producto"].obtener_configuracion()
        if componentes
        else None
    )
    precio_filamento_estandar = (
        max(_decimal(config.coste_plastico_kg), Decimal("0"))
        if config
        else Decimal("0")
    )
    tramo = (
        config.tramo_filamento_para_gramos(peso_total_gramos)
        if config
        else None
    )
    precio_filamento_kg = (
        config.precio_filamento_para_gramos(peso_total_gramos)
        if config
        else Decimal("0")
    )

    for componente in componentes:
        producto = componente["producto"]
        cantidad = max(int(componente.get("cantidad") or 0), 0)

        calculo = calcular_escenarios_producto(
            producto,
            cantidad,
            precio_filamento_kg=precio_filamento_kg,
        )
        costo_componente = calculo["costo_productivo_total"]
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
                "peso_total_gramos": calculo["peso_total_gramos"],
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
        "peso_total_gramos": peso_total_gramos,
        "precio_filamento_estandar_kg": precio_filamento_estandar,
        "precio_filamento_kg": precio_filamento_kg,
        "tramo_desde_gramos": (
            _decimal(tramo.desde_gramos)
            if tramo is not None
            else None
        ),
        "usa_filamento_volumen": (
            precio_filamento_kg < precio_filamento_estandar
            if precio_filamento_estandar > 0
            else False
        ),
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

    Cada producto hipotético se evalúa con la misma calculadora de cantidad,
    incluyendo el tramo de filamento que le corresponde por sus gramos totales.
    Luego se comparan el comportamiento promedio y el caso más exigente.
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
        calculo["costo_productivo_total"]
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
