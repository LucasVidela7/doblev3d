from decimal import Decimal

from calculadora.precios import (
    MARGEN_MINIMO,
    calcular_escenarios_kit_libre,
    calcular_escenarios_producto,
    redondear_arriba,
)
from productos.models import Producto

from .precio_fijo_combinado import calcular_escenarios_kit_fijo


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


EXTRA_MULTIPLO = Decimal("500")


def analizar_opciones_libres(
    productos,
    cantidad_productos,
    precio_kit,
    proteger_rentabilidad=True,
):
    """
    Clasifica las opciones de un kit libre según su capacidad de sostener
    el escenario Agresivo de la calculadora.

    Cada lugar del kit recibe una parte proporcional del precio base. Si un
    producto necesita más precio para sostener ese escenario, la diferencia
    se transforma en un extra redondeado hacia arriba. Sumando los extras de
    los productos seleccionados se mantiene una regla aditiva y predecible.
    """
    productos = list(productos)
    cantidad = max(int(cantidad_productos or 0), 0)
    precio = _decimal(precio_kit)

    resultado = {
        "disponible": False,
        "proteger_rentabilidad": bool(proteger_rentabilidad),
        "cantidad_productos": cantidad,
        "precio_kit": precio,
        "precio_base_por_lugar": Decimal("0"),
        "margen_piso": MARGEN_MINIMO,
        "incluidos": [],
        "premium": [],
        "opciones": [],
        "cantidad_incluidos": 0,
        "cantidad_premium": 0,
        "cantidad_requieren_extra": 0,
        "extra_minimo": Decimal("0"),
        "extra_maximo": Decimal("0"),
        "extra_sugerido_minimo": Decimal("0"),
        "extra_sugerido_maximo": Decimal("0"),
    }

    if cantidad <= 0 or precio <= 0 or not productos:
        return resultado

    divisor = Decimal(cantidad)
    precio_base_por_lugar = precio / divisor
    resultado["precio_base_por_lugar"] = precio_base_por_lugar

    extras_positivos = []
    extras_sugeridos = []

    for producto in productos:
        calculo = calcular_escenarios_producto(
            producto,
            cantidad,
            forzar_filamento_economico=True,
        )
        escenario_agresivo = calculo["escenarios"]["agresivo"]
        referencia_total = _decimal(
            escenario_agresivo["total_recomendado"]
        )
        referencia_por_lugar = (
            referencia_total / divisor
            if divisor > 0
            else Decimal("0")
        )

        extra_sugerido = Decimal("0")
        if referencia_por_lugar > precio_base_por_lugar:
            extra_sugerido = redondear_arriba(
                referencia_por_lugar - precio_base_por_lugar,
                EXTRA_MULTIPLO,
            )

        requiere_extra = extra_sugerido > 0
        extra_aplicado = (
            extra_sugerido
            if proteger_rentabilidad
            else Decimal("0")
        )

        opcion = {
            "producto": producto,
            "producto_id": producto.id,
            "codigo": producto.codigo,
            "nombre": producto.nombre,
            "precio_lista": _decimal(producto.subtotal),
            "costo_productivo": _decimal(
                calculo["costo_productivo"]
            ),
            "referencia_agresiva_por_lugar": referencia_por_lugar,
            "requiere_extra": requiere_extra,
            "incluido": not requiere_extra or not proteger_rentabilidad,
            "extra_sugerido": extra_sugerido,
            "extra": extra_aplicado,
            "precio_kit_con_extra": precio + extra_aplicado,
        }
        resultado["opciones"].append(opcion)

        if requiere_extra:
            extras_sugeridos.append(extra_sugerido)

        if requiere_extra and proteger_rentabilidad:
            resultado["premium"].append(opcion)
            extras_positivos.append(extra_aplicado)
        else:
            resultado["incluidos"].append(opcion)

    resultado["opciones"].sort(
        key=lambda item: (
            0 if item["incluido"] else 1,
            item["extra"],
            item["nombre"].casefold(),
            item["producto_id"],
        )
    )
    resultado["cantidad_incluidos"] = len(resultado["incluidos"])
    resultado["cantidad_premium"] = len(resultado["premium"])
    resultado["cantidad_requieren_extra"] = len(extras_sugeridos)
    resultado["extra_minimo"] = (
        min(extras_positivos)
        if extras_positivos
        else Decimal("0")
    )
    resultado["extra_maximo"] = (
        max(extras_positivos)
        if extras_positivos
        else Decimal("0")
    )
    resultado["extra_sugerido_minimo"] = (
        min(extras_sugeridos)
        if extras_sugeridos
        else Decimal("0")
    )
    resultado["extra_sugerido_maximo"] = (
        max(extras_sugeridos)
        if extras_sugeridos
        else Decimal("0")
    )
    resultado["disponible"] = True
    return resultado


def analizar_opciones_kit(kit, productos_categoria=None):
    if (
        kit.modalidad != "LIBRE_CATEGORIA"
        or not kit.tipo_producto_id
    ):
        return analizar_opciones_libres(
            [],
            getattr(kit, "cantidad_productos", 0),
            getattr(kit, "precio", 0),
            getattr(kit, "proteger_rentabilidad_libre", False),
        )

    productos = (
        list(productos_categoria)
        if productos_categoria is not None
        else _productos_categoria(kit)
    )

    return analizar_opciones_libres(
        productos,
        kit.cantidad_productos,
        kit.precio,
        getattr(kit, "proteger_rentabilidad_libre", False),
    )


def precio_automatico_kit_libre(kit, productos):
    """
    Precio unitario automático del kit para una selección concreta.
    Los extras se aplican por posición elegida y son aditivos.
    """
    if kit.modalidad != "LIBRE_CATEGORIA":
        return _decimal(kit.precio)

    seleccion = list(productos)
    if len(seleccion) != int(kit.cantidad_productos or 0):
        raise ValueError(
            f"El kit {kit.nombre} necesita {kit.cantidad_productos} productos."
        )

    analisis = analizar_opciones_kit(
        kit,
        productos_categoria=list(
            Producto.objects.filter(
                tipo_id=kit.tipo_producto_id,
                activo=True,
                solo_produccion=False,
            ).order_by("id")
        ),
    )
    opciones = {
        item["producto_id"]: item
        for item in analisis["opciones"]
    }

    total_extra = Decimal("0")
    for producto in seleccion:
        opcion = opciones.get(producto.id)
        if not opcion:
            raise ValueError(
                f"{producto.nombre} no está disponible para {kit.nombre}."
            )
        total_extra += _decimal(opcion["extra"])

    return _decimal(kit.precio) + total_extra


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
        "cantidad_total_calculada": 0,
        "margen_tope_ponderado": None,
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

        resultado["cantidad_total_calculada"] = int(
            calculo.get("cantidad_total", 0)
        )
        resultado["margen_tope_ponderado"] = _decimal(
            calculo.get("margen_tope_ponderado", MARGEN_MINIMO)
        ).quantize(Decimal("0.1"))
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
                "referencia_separada": _decimal(
                    escenario.get("referencia_separada", 0)
                ),
                "ahorro_combo": _decimal(
                    escenario.get("ahorro_combo", 0)
                ),
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
