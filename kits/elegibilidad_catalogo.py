from decimal import Decimal, ROUND_CEILING

from calculadora.precios import calcular_costo_productivo_producto

from .models import (
    MARGEN_MINIMO_KIT,
    MULTIPLO_PRECIO_KIT,
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


def _redondear_arriba(valor, multiplo=MULTIPLO_PRECIO_KIT):
    valor = _decimal(valor)
    multiplo = _decimal(multiplo)
    if valor <= 0 or multiplo <= 0:
        return Decimal("0")
    return (
        (valor / multiplo)
        .to_integral_value(rounding=ROUND_CEILING)
        * multiplo
    )


def costo_operativo_producto(producto):
    """Costo productivo vigente usado realmente por los kits.

    Los kits fuerzan el precio económico de filamento cuando está configurado,
    igual que la calculadora y el cálculo por volumen. Como respaldo para
    productos sin cálculo productivo se conserva costo + seguro del producto.
    """
    calculo = calcular_costo_productivo_producto(
        producto,
        cantidad=1,
        forzar_filamento_economico=True,
    )
    costo = max(
        _decimal(calculo.get("costo_productivo")),
        Decimal("0"),
    )

    if costo <= 0:
        costo = max(
            _decimal(getattr(producto, "costo", 0))
            + _decimal(getattr(producto, "seguro", 0)),
            Decimal("0"),
        )

    return costo


def costo_maximo_unitario(kit, margen_minimo=MARGEN_MINIMO_KIT):
    """Costo máximo por posición incluido en el precio base del kit."""
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


def adicional_producto_kit(
    kit,
    producto,
    margen_minimo=MARGEN_MINIMO_KIT,
):
    """Adicional comercial necesario para una opción por encima del presupuesto.

    Sólo se cobra el exceso de costo respecto de la posición ya incluida en el
    kit. Ese exceso se lleva al mismo margen mínimo y se redondea al múltiplo
    comercial de kits. De este modo la opción premium conserva la ventaja del
    combo sin trasladar al cliente el precio individual completo.
    """
    if kit.modalidad == "FIJO":
        return Decimal("0")

    limite = costo_maximo_unitario(
        kit,
        margen_minimo=margen_minimo,
    )
    costo = costo_operativo_producto(producto)
    exceso = max(costo - limite, Decimal("0"))

    if exceso <= 0:
        return Decimal("0")

    proporcion = Decimal("1") - (
        _decimal(margen_minimo) / Decimal("100")
    )
    if proporcion <= 0:
        return Decimal("0")

    return _redondear_arriba(
        exceso / proporcion,
        MULTIPLO_PRECIO_KIT,
    )


def producto_es_elegible_para_kit(
    kit,
    producto,
    margen_minimo=MARGEN_MINIMO_KIT,
):
    """Indica si el producto queda incluido sin adicional en el precio base."""
    if kit.modalidad == "FIJO":
        return True

    if (
        not kit.tipo_producto_id
        or not getattr(producto, "activo", False)
        or getattr(producto, "solo_produccion", False)
        or producto.tipo_id != kit.tipo_producto_id
    ):
        return False

    return adicional_producto_kit(
        kit,
        producto,
        margen_minimo=margen_minimo,
    ) <= 0


def productos_elegibles_para_kit(
    kit,
    productos,
    margen_minimo=MARGEN_MINIMO_KIT,
):
    """Opciones incluidas sin adicional dentro del precio base."""
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


def opciones_producto_kit(kit, productos):
    """Devuelve todas las opciones comerciales con su adicional, si corresponde."""
    cantidad = max(int(kit.cantidad_productos or 0), 1)
    precio_base = _decimal(kit.precio)
    precio_base_posicion = (
        precio_base / Decimal(cantidad)
        if cantidad > 0
        else Decimal("0")
    )

    opciones = []
    for producto in productos:
        if (
            not getattr(producto, "activo", False)
            or getattr(producto, "solo_produccion", False)
            or (
                kit.tipo_producto_id
                and producto.tipo_id != kit.tipo_producto_id
            )
        ):
            continue

        costo = costo_operativo_producto(producto)
        adicional = adicional_producto_kit(kit, producto)
        precio_equivalente = precio_base_posicion + adicional
        precio_individual = _decimal(getattr(producto, "subtotal", 0))
        ahorro_vs_individual = max(
            precio_individual - precio_equivalente,
            Decimal("0"),
        )

        costo_escenario = costo * Decimal(cantidad)
        precio_escenario = (
            precio_base
            + adicional * Decimal(cantidad)
        )

        opciones.append(
            {
                "producto": producto,
                "costo": costo,
                "adicional": adicional,
                "incluido": adicional <= 0,
                "precio_equivalente": precio_equivalente,
                "precio_individual": precio_individual,
                "ahorro_vs_individual": ahorro_vs_individual,
                "margen_escenario": _margen(
                    costo_escenario,
                    precio_escenario,
                ),
            }
        )

    return opciones


def precio_kit_con_seleccion(kit, productos):
    """Precio unitario automático del kit para una selección concreta."""
    precio = _decimal(kit.precio)
    if kit.modalidad == "FIJO":
        return precio

    return precio + sum(
        (
            adicional_producto_kit(kit, producto)
            for producto in productos
        ),
        Decimal("0"),
    )


def resumen_elegibilidad_kit(kit, productos):
    """Resumen económico real de las opciones que el cliente puede seleccionar."""
    candidatos = list(productos)
    opciones = opciones_producto_kit(
        kit,
        candidatos,
    )
    incluidas = [
        opcion
        for opcion in opciones
        if opcion["incluido"]
    ]
    premium = [
        opcion
        for opcion in opciones
        if not opcion["incluido"]
    ]

    cantidad = max(int(kit.cantidad_productos or 0), 1)
    precio_base = _decimal(kit.precio)

    if opciones:
        costo_promedio_opcion = (
            sum(
                (opcion["costo"] for opcion in opciones),
                Decimal("0"),
            )
            / Decimal(len(opciones))
        )
        adicional_promedio = (
            sum(
                (opcion["adicional"] for opcion in opciones),
                Decimal("0"),
            )
            / Decimal(len(opciones))
        )
        costo_promedio_combinacion = (
            costo_promedio_opcion * Decimal(cantidad)
        )
        precio_promedio_combinacion = (
            precio_base
            + adicional_promedio * Decimal(cantidad)
        )
        margen_promedio_efectivo = _margen(
            costo_promedio_combinacion,
            precio_promedio_combinacion,
        )
        margenes = [
            opcion["margen_escenario"]
            for opcion in opciones
            if opcion["margen_escenario"] is not None
        ]
        margen_peor_efectivo = min(margenes) if margenes else None
    else:
        costo_promedio_opcion = Decimal("0")
        adicional_promedio = Decimal("0")
        margen_promedio_efectivo = None
        margen_peor_efectivo = None

    adicionales = [
        opcion["adicional"]
        for opcion in premium
        if opcion["adicional"] > 0
    ]

    return {
        # Compatibilidad: "productos" sigue significando opciones incluidas.
        "productos": [
            opcion["producto"]
            for opcion in incluidas
        ],
        "productos_premium": [
            opcion["producto"]
            for opcion in premium
        ],
        "opciones": opciones,
        "cantidad": len(incluidas),
        "cantidad_premium": len(premium),
        "cantidad_total": len(opciones),
        "cantidad_excluida": 0,
        "costo_maximo_unitario": costo_maximo_unitario(kit),
        "costo_promedio_opcion": costo_promedio_opcion,
        "adicional_promedio": adicional_promedio,
        "adicional_minimo": (
            min(adicionales)
            if adicionales
            else Decimal("0")
        ),
        "adicional_maximo": (
            max(adicionales)
            if adicionales
            else Decimal("0")
        ),
        "margen_promedio_efectivo": margen_promedio_efectivo,
        "margen_peor_efectivo": margen_peor_efectivo,
        "margen_minimo": MARGEN_MINIMO_KIT,
    }


def preparar_kits_catalogo(kits, productos_por_tipo):
    """Adjunta opciones base y premium; sólo oculta kits sin productos posibles."""
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

        kit.catalogo_productos_elegibles = resumen["productos"]
        kit.catalogo_productos_premium = resumen["productos_premium"]
        kit.catalogo_opciones = resumen["opciones"]
        kit.catalogo_cantidad_opciones = resumen["cantidad"]
        kit.catalogo_cantidad_premium = resumen["cantidad_premium"]
        kit.catalogo_cantidad_total = resumen["cantidad_total"]
        kit.catalogo_costo_maximo_unitario = resumen[
            "costo_maximo_unitario"
        ]

        if not resumen["opciones"]:
            continue

        # Todas son seleccionables: las premium llevan adicional.
        productos_por_kit[kit.id] = [
            opcion["producto"]
            for opcion in resumen["opciones"]
        ]
        publicados.append(kit)

    return publicados, productos_por_kit
