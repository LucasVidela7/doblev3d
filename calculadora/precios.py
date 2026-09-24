from decimal import Decimal, ROUND_CEILING
from math import log10

from productos.models import redondeo_precio_producto_actual

MARGEN_MINIMO = Decimal("22.5")
CANTIDAD_PISO_MARGEN = Decimal("1500")
DIFERENCIA_ESCENARIO = Decimal("4")
CANTIDAD_FILAMENTO_ECONOMICO = 5
CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS = 5
DESCUENTO_MAXIMO_PRODUCTOS = Decimal("15")
SUAVIDAD_DESCUENTO_PRODUCTOS = Decimal("3")
MAX_CANTIDAD_CATALOGO = 20


def redondear_arriba(valor, multiplo=None):
    valor = Decimal(valor)
    multiplo = (
        redondeo_precio_producto_actual()
        if multiplo is None
        else Decimal(multiplo)
    )
    if valor <= 0:
        return Decimal("0")
    return (
        (valor / multiplo).to_integral_value(rounding=ROUND_CEILING)
        * multiplo
    )


def descuento_dinamico_por_cantidad(
    descuento_tecnico,
    cantidad,
    cantidad_inicio,
    tope=Decimal("15"),
    suavidad=Decimal("3"),
):
    """
    Libera de forma suave el descuento técnico disponible.

    El descuento no nace de una tabla fija. Primero se calcula cuánto descuento
    soporta realmente el producto/kit según costos y margen; luego la cantidad
    habilita una porción creciente de ese beneficio con una curva asintótica.

    - antes de cantidad_inicio: 0%
    - en el umbral: se habilita una fracción pequeña
    - al crecer la cantidad: se acerca gradualmente al descuento técnico
    - nunca supera el tope comercial
    """
    cantidad = max(int(cantidad or 0), 0)
    cantidad_inicio = max(int(cantidad_inicio or 1), 1)
    tecnico = max(Decimal(str(descuento_tecnico or 0)), Decimal("0"))
    tope = max(Decimal(str(tope or 0)), Decimal("0"))
    suavidad = max(Decimal(str(suavidad or 0)), Decimal("0"))

    if cantidad < cantidad_inicio or tecnico <= 0 or tope <= 0:
        return Decimal("0")

    disponible = min(tecnico, tope)
    progreso = Decimal(cantidad - cantidad_inicio + 1)
    divisor = progreso + suavidad
    if divisor <= 0:
        return disponible.quantize(Decimal("0.1"))

    factor = progreso / divisor
    return (disponible * factor).quantize(Decimal("0.1"))


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


def calcular_costo_productivo_producto(
    producto,
    cantidad=1,
    forzar_filamento_economico=False,
):
    """Recalcula el costo sin modificar el costo minorista del producto.

    El precio estándar de filamento sigue siendo la referencia de lista.
    La calculadora usa el precio económico desde 5 unidades, y los kits
    pueden forzarlo aunque cada componente aparezca una sola vez.
    """
    cantidad = max(int(cantidad or 1), 1)
    cero = Decimal("0")
    costo_insumos = Decimal(
        str(getattr(producto, "costo_insumos_total", 0) or 0)
    )

    if not producto.requiere_impresion:
        return {
            "config": None,
            "cantidad": cantidad,
            "horas_totales": cero,
            "peso_gramos": cero,
            "precio_filamento_kg": cero,
            "filamento_economico": False,
            "tipo_filamento": "estandar",
            "costo_luz": cero,
            "costo_material": cero,
            "amortizacion": cero,
            "provision_fallos": cero,
            "costo": cero,
            "seguro": cero,
            "costo_insumos": costo_insumos,
            "costo_productivo": costo_insumos,
        }

    config = producto.obtener_configuracion()
    if not config:
        return {
            "config": None,
            "cantidad": cantidad,
            "horas_totales": cero,
            "peso_gramos": Decimal(str(producto.peso_gramos or 0)),
            "precio_filamento_kg": cero,
            "filamento_economico": False,
            "tipo_filamento": "estandar",
            "costo_luz": cero,
            "costo_material": cero,
            "amortizacion": cero,
            "provision_fallos": cero,
            "costo": cero,
            "seguro": cero,
            "costo_insumos": costo_insumos,
            "costo_productivo": costo_insumos,
        }

    precio_estandar = max(
        Decimal(str(config.coste_plastico_kg or 0)),
        cero,
    )
    precio_cantidad_configurado = max(
        Decimal(str(config.coste_plastico_kg_cantidad or 0)),
        cero,
    )
    precio_cantidad = Decimal(
        str(config.coste_plastico_kg_cantidad_efectivo)
    )

    solicitar_economico = (
        bool(forzar_filamento_economico)
        or cantidad >= CANTIDAD_FILAMENTO_ECONOMICO
    )
    filamento_economico = (
        solicitar_economico
        and precio_cantidad_configurado > 0
        and (
            precio_estandar <= 0
            or precio_cantidad < precio_estandar
        )
    )
    precio_filamento = (
        precio_cantidad
        if filamento_economico
        else precio_estandar
    )

    horas_totales = Decimal(str(producto.horas_totales or 0))
    peso_gramos = max(
        Decimal(str(producto.peso_gramos or 0)),
        cero,
    )

    # Los productos compuestos se calculan desde sus piezas reales para no
    # depender de que horas/peso agregados hayan quedado sincronizados.
    if getattr(producto, "es_compuesto", False) and producto.pk:
        peso_componentes = Decimal("0")
        for relacion in producto.componentes.select_related("componente").all():
            cantidad_componente = Decimal(int(relacion.cantidad or 0))
            peso_componentes += (
                Decimal(str(relacion.componente.peso_gramos or 0))
                * cantidad_componente
            )
        if peso_componentes > 0:
            peso_gramos = peso_componentes
    costo_luz = horas_totales * Decimal(str(config.coste_luz_hora or 0))
    costo_material = (
        peso_gramos
        * precio_filamento
        / Decimal("1000")
    )
    costo = costo_luz + costo_material
    amortizacion = (
        horas_totales
        * Decimal(str(config.coste_amortizacion_hora or 0))
    )
    tasa_fallos = (
        Decimal(str(config.tasa_fallos or 0))
        / Decimal("100")
    )
    provision_fallos = (amortizacion + costo) * tasa_fallos
    seguro = amortizacion + provision_fallos

    return {
        "config": config,
        "cantidad": cantidad,
        "horas_totales": horas_totales,
        "peso_gramos": peso_gramos,
        "precio_filamento_kg": precio_filamento,
        "precio_filamento_estandar_kg": precio_estandar,
        "precio_filamento_cantidad_kg": precio_cantidad,
        "filamento_economico": filamento_economico,
        "tipo_filamento": (
            "cantidad"
            if filamento_economico
            else "estandar"
        ),
        "costo_luz": costo_luz,
        "costo_material": costo_material,
        "amortizacion": amortizacion,
        "provision_fallos": provision_fallos,
        "costo": costo,
        "seguro": seguro,
        "costo_insumos": costo_insumos,
        "costo_productivo": costo + seguro + costo_insumos,
    }


def calcular_precio_catalogo_producto(producto, cantidad):
    """
    Precio final de un producto exactamente como se publica/cotiza en el carrito.

    Reglas vigentes:
    - 1 a 4 unidades: precio de lista.
    - desde 5: descuento dinámico según el beneficio técnico disponible.
    - tope comercial de descuento: 15%.
    - el costo por cantidad puede usar filamento económico desde 5 unidades.
    """
    cantidad = max(int(cantidad or 1), 1)

    precio_lista_unitario = Decimal(str(producto.subtotal or 0))
    precio_lista_total = precio_lista_unitario * Decimal(cantidad)

    calculo = calcular_escenarios_producto(producto, cantidad)
    desglose = calculo["desglose"]
    costo_productivo_unitario = Decimal(str(calculo["costo_productivo"] or 0))
    costo_total = costo_productivo_unitario * Decimal(cantidad)

    recomendado = Decimal(str(
        calculo["escenarios"]["recomendado"]["total_recomendado"] or 0
    ))
    precio_tecnico_total = (
        min(precio_lista_total, recomendado)
        if recomendado > 0
        else precio_lista_total
    )

    descuento_tecnico = Decimal("0")
    descuento_dinamico = Decimal("0")
    precio_final_total = precio_lista_total

    if (
        cantidad >= CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS
        and precio_lista_total > 0
    ):
        descuento_tecnico = (
            (precio_lista_total - precio_tecnico_total)
            / precio_lista_total
            * Decimal("100")
        )
        descuento_dinamico = descuento_dinamico_por_cantidad(
            descuento_tecnico,
            cantidad,
            CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS,
            tope=DESCUENTO_MAXIMO_PRODUCTOS,
            suavidad=SUAVIDAD_DESCUENTO_PRODUCTOS,
        )
        precio_minimo_comercial = (
            precio_lista_total
            * (
                Decimal("1")
                - descuento_dinamico / Decimal("100")
            )
        ).quantize(Decimal("0.01"))

        precio_final_total = min(
            precio_lista_total,
            max(precio_minimo_comercial, precio_tecnico_total),
        )

    precio_unitario = (
        precio_final_total / Decimal(cantidad)
    ).quantize(Decimal("0.01"))
    precio_final_total = precio_unitario * Decimal(cantidad)

    ahorro = max(
        precio_lista_total - precio_final_total,
        Decimal("0"),
    )
    descuento_porcentaje = (
        (ahorro / precio_lista_total * Decimal("100"))
        .quantize(Decimal("0.1"))
        if precio_lista_total > 0
        else Decimal("0")
    )
    ganancia = precio_final_total - costo_total
    margen_real = (
        ganancia / precio_final_total * Decimal("100")
        if precio_final_total > 0
        else Decimal("0")
    )

    return {
        "cantidad": cantidad,
        "precio_lista_unitario": precio_lista_unitario,
        "precio_lista_total": precio_lista_total,
        "precio_tecnico_total": precio_tecnico_total,
        "precio_unitario": precio_unitario,
        "precio_final_total": precio_final_total,
        "ahorro": ahorro,
        "descuento_tecnico": descuento_tecnico,
        "descuento_porcentaje": descuento_porcentaje,
        "descuento_dinamico": descuento_dinamico,
        "costo_productivo_unitario": costo_productivo_unitario,
        "costo_total": costo_total,
        "ganancia": ganancia,
        "margen_real": margen_real,
        "desglose": desglose,
        "filamento_economico": calculo["filamento_economico"],
        "precio_filamento_kg": calculo["precio_filamento_kg"],
        "aplica_descuento": ahorro > 0,
    }


def calcular_escenarios_producto(
    producto,
    cantidad,
    forzar_filamento_economico=False,
):
    cantidad = max(int(cantidad or 1), 1)

    desglose = calcular_costo_productivo_producto(
        producto,
        cantidad,
        forzar_filamento_economico=forzar_filamento_economico,
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
        "precio_filamento_kg": desglose["precio_filamento_kg"],
        "filamento_economico": desglose["filamento_economico"],
        "tipo_filamento": desglose["tipo_filamento"],
        "desglose": desglose,
        "margen_tope": margen_tope,
        "margen_piso": MARGEN_MINIMO,
        "escenarios": escenarios,
    }


def calcular_escenarios_kit_fijo(componentes):
    """Calcula un kit fijo con la misma lógica comercial de la calculadora.

    Los kits usan siempre el costo de filamento para cantidad cuando está
    configurado, aunque un componente aparezca sólo una vez.
    """
    acumulados = {
        "agresivo": Decimal("0"),
        "recomendado": Decimal("0"),
        "conservador": Decimal("0"),
    }
    costo_total = Decimal("0")
    detalle = []
    precio_filamento_kg = Decimal("0")
    filamento_economico = False

    for componente in componentes:
        producto = componente["producto"]
        cantidad = max(int(componente.get("cantidad") or 0), 0)

        if cantidad <= 0:
            continue

        calculo = calcular_escenarios_producto(
            producto,
            cantidad,
            forzar_filamento_economico=True,
        )
        costo_componente = (
            calculo["costo_productivo"]
            * Decimal(cantidad)
        )
        costo_total += costo_componente

        if calculo["precio_filamento_kg"] > 0:
            precio_filamento_kg = calculo["precio_filamento_kg"]
        filamento_economico = (
            filamento_economico
            or calculo["filamento_economico"]
        )

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
                "precio_filamento_kg": calculo["precio_filamento_kg"],
                "filamento_economico": calculo["filamento_economico"],
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


def _margen_real(costo, precio):
    costo = Decimal(str(costo or 0))
    precio = Decimal(str(precio or 0))
    if precio <= 0:
        return Decimal("0")
    return (precio - costo) / precio * Decimal("100")


def calcular_escenarios_kit_libre(productos, cantidad):
    """Sugiere precios para un kit libre por categoría.

    Como todavía no sabemos qué productos elegirá el cliente, se calculan dos
    referencias de costo: el promedio de la categoría y el peor caso. Todos
    los productos se valorizan con el filamento para cantidad cuando existe.
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
            "precio_filamento_kg": Decimal("0"),
            "filamento_economico": False,
            "tipo_filamento": "estandar",
            "escenarios": {},
            "productos": [],
        }

    calculos = [
        calcular_escenarios_producto(
            producto,
            cantidad,
            forzar_filamento_economico=True,
        )
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
    )
    recomendado_promedio = redondear_arriba(
        sum(precios_recomendados, Decimal("0")) / divisor,
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

    precio_filamento_kg = next(
        (
            calculo["precio_filamento_kg"]
            for calculo in calculos
            if calculo["precio_filamento_kg"] > 0
        ),
        Decimal("0"),
    )
    filamento_economico = any(
        calculo["filamento_economico"]
        for calculo in calculos
    )

    return {
        "cantidad": cantidad,
        "cantidad_productos_categoria": len(calculos),
        "costo_promedio": costo_promedio,
        "costo_peor_caso": costo_peor,
        "margen_piso": MARGEN_MINIMO,
        "precio_filamento_kg": precio_filamento_kg,
        "filamento_economico": filamento_economico,
        "tipo_filamento": (
            "cantidad"
            if filamento_economico
            else "estandar"
        ),
        "escenarios": escenarios,
        "productos": calculos,
    }
