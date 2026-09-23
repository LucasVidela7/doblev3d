from collections import Counter
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from calculadora.precios import (
    MARGEN_MINIMO,
    calcular_costo_productivo_producto,
    descuento_dinamico_por_cantidad,
    margen_sugerido,
    margenes_escenario,
    precio_mayorista,
    redondear_arriba,
)
from kits.engine import KitEngine
from kits.models import Kit
from productos.models import Producto


CANTIDAD_MINIMA_KITS_VOLUMEN = 2
DESCUENTO_MAXIMO_KITS = Decimal("15")
SUAVIDAD_DESCUENTO_KITS = Decimal("3")


def _decimal(valor):
    try:
        return Decimal(str(valor or 0))
    except (TypeError, ValueError):
        return Decimal("0")


def _redondear_centavos(valor, modo=ROUND_HALF_UP):
    return _decimal(valor).quantize(Decimal("0.01"), rounding=modo)


def _costo_unitario_volumen(producto, cantidad):
    """
    Costo productivo real para ventas de kits.

    Los kits fuerzan el filamento económico cuando está configurado.
    Para productos sin cálculo productivo se conserva como respaldo el
    costo + seguro actual del producto.
    """
    calculo = calcular_costo_productivo_producto(
        producto,
        cantidad=max(int(cantidad or 1), 1),
        forzar_filamento_economico=True,
    )
    costo = max(_decimal(calculo.get("costo_productivo")), Decimal("0"))

    if costo <= 0:
        costo = max(
            _decimal(getattr(producto, "costo", 0))
            + _decimal(getattr(producto, "seguro", 0)),
            Decimal("0"),
        )

    return costo


def _preparar_linea(item):
    kit = item["kit"]
    cantidad_kits = max(int(item.get("cantidad") or 0), 0)
    componentes = list(item.get("componentes") or [])

    precio_unitario_lista = max(
        _decimal(
            item.get(
                "precio_unitario_lista",
                kit.precio,
            )
        ),
        Decimal("0"),
    )
    precio_lista_total = precio_unitario_lista * Decimal(cantidad_kits)

    costo_total = Decimal("0")
    piezas = 0
    ponderacion_margen = Decimal("0")
    detalle_componentes = []

    for componente in componentes:
        producto = componente["producto"]
        cantidad = max(int(componente.get("cantidad") or 0), 0)
        if cantidad <= 0:
            continue

        costo_unitario = _costo_unitario_volumen(producto, cantidad)
        costo_componente = costo_unitario * Decimal(cantidad)
        margen_producto = max(
            _decimal(getattr(producto, "margen_ganancia", 0)),
            MARGEN_MINIMO,
        )

        costo_total += costo_componente
        piezas += cantidad
        ponderacion_margen += costo_componente * margen_producto

        detalle_componentes.append(
            {
                "producto_id": producto.id,
                "cantidad": cantidad,
                "costo_unitario": costo_unitario,
                "costo_total": costo_componente,
                "margen": margen_producto,
            }
        )

    margen_ponderado = (
        ponderacion_margen / costo_total
        if costo_total > 0
        else MARGEN_MINIMO
    )

    precio_piso_total = redondear_arriba(
        precio_mayorista(costo_total, MARGEN_MINIMO),
        Decimal("100"),
    )

    # Referencia técnica de una unidad del kit. La usamos únicamente para
    # determinar qué porcentaje de descuento corresponde por volumen. El
    # importe final se calcula sobre el precio real configurado del kit.
    precio_referencia_conservador_unitario = Decimal("0")
    precio_referencia_conservador_total = Decimal("0")
    margen_conservador_referencia = margen_ponderado

    if cantidad_kits > 0 and piezas > 0 and costo_total > 0:
        divisor = Decimal(cantidad_kits)
        costo_por_kit = costo_total / divisor
        piezas_por_kit = max(
            int(
                (Decimal(piezas) / divisor).to_integral_value(
                    rounding=ROUND_CEILING
                )
            ),
            1,
        )
        margen_conservador_referencia = margenes_escenario(
            piezas_por_kit,
            margen_ponderado,
        )["conservador"]
        precio_referencia_conservador_unitario = redondear_arriba(
            precio_mayorista(costo_por_kit, margen_conservador_referencia),
            Decimal("100"),
        )
        precio_referencia_conservador_total = (
            precio_referencia_conservador_unitario * divisor
        )

    # Nunca se sube automáticamente un precio de lista que ya esté por debajo
    # del piso. En ese caso la línea simplemente no tiene capacidad de descuento.
    piso_aplicable = min(precio_piso_total, precio_lista_total)
    capacidad_descuento = max(
        precio_lista_total - piso_aplicable,
        Decimal("0"),
    )

    premium_mercado_porcentaje = Decimal("0")
    if (
        precio_referencia_conservador_unitario > 0
        and precio_unitario_lista > precio_referencia_conservador_unitario
    ):
        premium_mercado_porcentaje = (
            (
                precio_unitario_lista
                / precio_referencia_conservador_unitario
                - Decimal("1")
            )
            * Decimal("100")
        ).quantize(Decimal("0.1"))

    return {
        "key": str(item.get("key") or ""),
        "detalle": item.get("detalle"),
        "kit": kit,
        "cantidad_kits": cantidad_kits,
        "componentes": detalle_componentes,
        "piezas": piezas,
        "precio_unitario_lista": precio_unitario_lista,
        "precio_lista_total": precio_lista_total,
        "costo_total": costo_total,
        "margen_ponderado": margen_ponderado,
        "margen_conservador_referencia": margen_conservador_referencia,
        "precio_referencia_conservador_unitario": (
            precio_referencia_conservador_unitario
        ),
        "precio_referencia_conservador_total": (
            precio_referencia_conservador_total
        ),
        "premium_mercado_porcentaje": premium_mercado_porcentaje,
        "precio_piso_total": precio_piso_total,
        "piso_aplicable": piso_aplicable,
        "capacidad_descuento": capacidad_descuento,
    }


def calcular_precio_volumen_kits(items):
    """
    Calcula un único precio mayorista para el conjunto de kits del pedido.

    Reglas:
    - La lógica se activa desde 2 kits totales.
    - Desde 2 kits libera progresivamente el descuento que soporta el margen
      real disponible, con la referencia técnica como guía cuando corresponde.
    - La intensidad depende tanto de la cantidad de kits como de la cantidad
      REAL de productos contenidos y del margen disponible.
    - El beneficio comercial tiene un tope de 15%.
    - Ese porcentaje se aplica sobre el precio real configurado de los kits,
      conservando así su posicionamiento de mercado.
    - El descuento nunca baja una línea por debajo de MARGEN_MINIMO.
    - Si el precio actual ya está por debajo del piso, no se lo aumenta ni se
      lo descuenta automáticamente.
    """
    lineas = [
        _preparar_linea(item)
        for item in items
        if int(item.get("cantidad") or 0) > 0
    ]

    total_kits = sum(linea["cantidad_kits"] for linea in lineas)
    total_piezas = sum(linea["piezas"] for linea in lineas)
    precio_lista_total = sum(
        (linea["precio_lista_total"] for linea in lineas),
        Decimal("0"),
    )
    costo_total = sum(
        (linea["costo_total"] for linea in lineas),
        Decimal("0"),
    )
    precio_referencia_conservador_total = sum(
        (
            linea["precio_referencia_conservador_total"]
            for linea in lineas
        ),
        Decimal("0"),
    )

    if costo_total > 0:
        margen_tope_ponderado = (
            sum(
                (
                    linea["costo_total"] * linea["margen_ponderado"]
                    for linea in lineas
                ),
                Decimal("0"),
            )
            / costo_total
        )
    else:
        margen_tope_ponderado = MARGEN_MINIMO

    margen_tope_ponderado = max(
        margen_tope_ponderado,
        MARGEN_MINIMO,
    ).quantize(Decimal("0.1"))

    elegible = (
        total_kits >= CANTIDAD_MINIMA_KITS_VOLUMEN
        and total_piezas > 0
        and precio_lista_total > 0
        and costo_total > 0
    )

    margen_objetivo = (
        margen_sugerido(total_piezas, margen_tope_ponderado)
        if elegible
        else margen_tope_ponderado
    )

    # Precio técnico puro: es lo que daría el cálculo anterior mirando sólo
    # costo + margen. Se conserva como piso de referencia, pero ya no reemplaza
    # directamente al precio real fijado por mercado.
    precio_objetivo_tecnico_total = (
        redondear_arriba(
            precio_mayorista(costo_total, margen_objetivo),
            Decimal("100"),
        )
        if elegible
        else precio_lista_total
    )

    descuento_referencia = Decimal("0")
    if (
        elegible
        and precio_referencia_conservador_total > 0
        and precio_objetivo_tecnico_total < precio_referencia_conservador_total
    ):
        descuento_referencia = (
            precio_referencia_conservador_total
            - precio_objetivo_tecnico_total
        ) / precio_referencia_conservador_total
        descuento_referencia = max(
            min(descuento_referencia, Decimal("1")),
            Decimal("0"),
        )

    descuento_referencia_porcentaje = (
        descuento_referencia * Decimal("100")
    ).quantize(Decimal("0.1"))

    # El mismo porcentaje técnico se aplica al precio de lista REAL. Así, si
    # un kit se vende por encima de la recomendación conservadora porque el
    # mercado valida ese valor, ese diferencial no se regala por cantidad.
    if elegible and descuento_referencia > 0:
        objetivo_desde_precio_real = redondear_arriba(
            precio_lista_total * (Decimal("1") - descuento_referencia),
            Decimal("100"),
        )
        precio_objetivo_total = min(
            precio_lista_total,
            max(precio_objetivo_tecnico_total, objetivo_desde_precio_real),
        )
    else:
        precio_objetivo_total = precio_lista_total

    descuento_tecnico_real = (
        (
            precio_lista_total - precio_objetivo_total
        )
        / precio_lista_total
        * Decimal("100")
        if elegible and precio_lista_total > 0
        else Decimal("0")
    )
    capacidad_total = sum(
        (linea["capacidad_descuento"] for linea in lineas),
        Decimal("0"),
    )
    descuento_soportable_por_margen = (
        capacidad_total
        / precio_lista_total
        * Decimal("100")
        if elegible and precio_lista_total > 0
        else Decimal("0")
    )

    # La referencia técnica sigue siendo la guía principal. Si el precio real
    # ya está por debajo de esa referencia, antes la curva quedaba en 0% aun
    # cuando todavía había margen rentable disponible. En ese caso usamos la
    # capacidad real hasta el piso operativo para que el beneficio comience
    # efectivamente desde la segunda unidad.
    descuento_curva_disponible = (
        descuento_tecnico_real
        if descuento_tecnico_real > 0
        else descuento_soportable_por_margen
    )
    descuento_maximo_comercial = descuento_dinamico_por_cantidad(
        descuento_curva_disponible,
        total_kits,
        CANTIDAD_MINIMA_KITS_VOLUMEN,
        tope=DESCUENTO_MAXIMO_KITS,
        suavidad=SUAVIDAD_DESCUENTO_KITS,
    )
    precio_curva_sin_redondear = (
        _redondear_centavos(
            precio_lista_total
            * (
                Decimal("1")
                - descuento_maximo_comercial / Decimal("100")
            )
        )
        if elegible
        else precio_lista_total
    )
    precio_minimo_comercial_total = (
        redondear_arriba(
            precio_curva_sin_redondear,
            Decimal("100"),
        )
        if elegible
        else precio_lista_total
    )

    # En compras pequeñas un descuento dinámico válido puede ser menor que
    # $100 sobre el total. Redondear siempre hacia arriba lo borraría por
    # completo (por ejemplo, $10.000 -> $9.950 -> $10.000). En ese único caso
    # conservamos el importe de la curva con precisión de centavos para que
    # desde la segunda unidad exista un beneficio real sin exceder el margen.
    if (
        elegible
        and descuento_maximo_comercial > 0
        and precio_curva_sin_redondear < precio_lista_total
        and precio_minimo_comercial_total >= precio_lista_total
    ):
        precio_minimo_comercial_total = precio_curva_sin_redondear

    # Cuando existe una baja técnica, la curva limita cuánto se libera por
    # cantidad. Si la referencia técnica no habilita baja pero todavía existe
    # margen real, la propia curva comercial define el descuento.
    if descuento_tecnico_real > 0:
        precio_objetivo_total = min(
            precio_lista_total,
            max(precio_objetivo_total, precio_minimo_comercial_total),
        )
    else:
        precio_objetivo_total = min(
            precio_lista_total,
            precio_minimo_comercial_total,
        )

    ajustado_por_precio_real = (
        elegible
        and precio_objetivo_total > precio_objetivo_tecnico_total
        and precio_lista_total > precio_referencia_conservador_total
    )

    ahorro_deseado = (
        max(precio_lista_total - precio_objetivo_total, Decimal("0"))
        if elegible
        else Decimal("0")
    )

    # El descuento de una compra de kits es único y equitativo: todas las
    # líneas reciben el mismo porcentaje. Para conservar la rentabilidad,
    # ese porcentaje común queda limitado por la línea con menor capacidad
    # de descuento. Así una combinación más rentable no subsidia a otra,
    # pero tampoco mostramos porcentajes distintos para la misma compra.
    descuento_deseado_porcentaje = (
        ahorro_deseado
        / precio_lista_total
        * Decimal("100")
        if elegible and precio_lista_total > 0
        else Decimal("0")
    )

    capacidades_porcentaje = [
        (
            linea["capacidad_descuento"]
            / linea["precio_lista_total"]
            * Decimal("100")
        )
        for linea in lineas
        if linea["precio_lista_total"] > 0
    ]
    descuento_equilibrado_porcentaje = (
        min(
            [descuento_deseado_porcentaje]
            + capacidades_porcentaje
        )
        if capacidades_porcentaje
        else Decimal("0")
    )
    descuento_equilibrado_porcentaje = max(
        descuento_equilibrado_porcentaje,
        Decimal("0"),
    )

    ahorro_aplicable = (
        precio_lista_total
        * descuento_equilibrado_porcentaje
        / Decimal("100")
    )
    limitado_por_margen = (
        descuento_equilibrado_porcentaje
        < descuento_deseado_porcentaje
    )

    for linea in lineas:
        if (
            descuento_equilibrado_porcentaje <= 0
            or linea["cantidad_kits"] <= 0
            or linea["precio_lista_total"] <= 0
        ):
            precio_unitario = linea["precio_unitario_lista"]
        else:
            precio_unitario_minimo = (
                linea["piso_aplicable"]
                / Decimal(linea["cantidad_kits"])
            ).quantize(Decimal("0.01"), rounding=ROUND_CEILING)

            precio_unitario = (
                linea["precio_unitario_lista"]
                * (
                    Decimal("1")
                    - descuento_equilibrado_porcentaje / Decimal("100")
                )
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            precio_unitario = min(
                linea["precio_unitario_lista"],
                max(precio_unitario, precio_unitario_minimo),
            )

        precio_final_total = (
            precio_unitario * Decimal(linea["cantidad_kits"])
        )
        ahorro_real_linea = max(
            linea["precio_lista_total"] - precio_final_total,
            Decimal("0"),
        )

        linea["precio_unitario_final"] = precio_unitario
        linea["precio_final_total"] = precio_final_total
        linea["ahorro"] = ahorro_real_linea
        linea["descuento_porcentaje"] = (
            descuento_equilibrado_porcentaje
            if ahorro_real_linea > 0
            else Decimal("0")
        ).quantize(Decimal("0.1"))

    precio_final_total = sum(
        (linea["precio_final_total"] for linea in lineas),
        Decimal("0"),
    )
    ahorro = max(precio_lista_total - precio_final_total, Decimal("0"))
    descuento_porcentaje = (
        ahorro / precio_lista_total * Decimal("100")
        if precio_lista_total > 0
        else Decimal("0")
    ).quantize(Decimal("0.1"))

    margen_real = Decimal("0")
    if precio_final_total > 0:
        margen_real = (
            (precio_final_total - costo_total)
            / precio_final_total
            * Decimal("100")
        ).quantize(Decimal("0.1"))

    return {
        "elegible": elegible,
        "cantidad_minima_kits": CANTIDAD_MINIMA_KITS_VOLUMEN,
        "total_kits": total_kits,
        "total_piezas": total_piezas,
        "precio_lista_total": precio_lista_total,
        "costo_total": costo_total,
        "margen_tope_ponderado": margen_tope_ponderado,
        "margen_objetivo": margen_objetivo,
        "margen_minimo": MARGEN_MINIMO,
        "precio_referencia_conservador_total": (
            precio_referencia_conservador_total
        ),
        "precio_objetivo_tecnico_total": precio_objetivo_tecnico_total,
        "descuento_referencia_porcentaje": descuento_referencia_porcentaje,
        "descuento_maximo_comercial": descuento_maximo_comercial,
        "descuento_equilibrado_porcentaje": (
            descuento_equilibrado_porcentaje
        ).quantize(Decimal("0.1")),
        "ajustado_por_precio_real": ajustado_por_precio_real,
        "precio_objetivo_total": precio_objetivo_total,
        "precio_final_total": precio_final_total,
        "ahorro": ahorro,
        "descuento_porcentaje": descuento_porcentaje,
        "margen_real": margen_real,
        "limitado_por_margen": limitado_por_margen,
        "lineas": lineas,
    }


def items_desde_pedido(pedido):
    detalles = (
        pedido.detalles
        .filter(tipo_item="KIT")
        .select_related("kit")
        .prefetch_related("productos_kit__producto")
        .order_by("id")
    )

    items = []
    for detalle in detalles:
        componentes_guardados = list(
            detalle.productos_kit.all()
        )
        precio_unitario_lista = _decimal(
            detalle.kit.precio
        )

        if (
            detalle.kit.modalidad == "LIBRE_CATEGORIA"
            and detalle.cantidad > 0
        ):
            seleccion = []
            seleccion_valida = True

            for componente in componentes_guardados:
                total = int(componente.cantidad or 0)
                if (
                    total <= 0
                    or total % detalle.cantidad != 0
                ):
                    seleccion_valida = False
                    break

                repeticiones = total // detalle.cantidad
                seleccion.extend(
                    [componente.producto] * repeticiones
                )

            if (
                seleccion_valida
                and len(seleccion)
                == int(detalle.kit.cantidad_productos or 0)
            ):
                try:
                    precio_unitario_lista = (
                        KitEngine.precio_unitario(
                            detalle.kit,
                            productos=seleccion,
                        )
                    )
                except ValueError:
                    precio_unitario_lista = _decimal(
                        detalle.kit.precio
                    )

        items.append(
            {
                "key": str(detalle.id),
                "detalle": detalle,
                "kit": detalle.kit,
                "cantidad": detalle.cantidad,
                "precio_unitario_lista": precio_unitario_lista,
                "componentes": [
                    {
                        "producto": componente.producto,
                        "cantidad": componente.cantidad,
                    }
                    for componente in componentes_guardados
                ],
            }
        )
    return items


def aplicar_precio_volumen_pedido(pedido):
    """Recalcula y persiste únicamente el precio de las líneas KIT."""
    resumen = calcular_precio_volumen_kits(items_desde_pedido(pedido))

    for linea in resumen["lineas"]:
        detalle = linea.get("detalle")
        if not detalle:
            continue

        nuevo_precio = _redondear_centavos(linea["precio_unitario_final"])
        if detalle.precio_unitario != nuevo_precio:
            detalle.precio_unitario = nuevo_precio
            detalle.save(update_fields=["precio_unitario"])

    return resumen


def items_desde_payload(payload):
    """Valida la selección actual del formulario para la vista previa."""
    items_payload = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items_payload, list):
        raise ValueError("Formato de items no válido.")

    items = []

    for bruto in items_payload:
        if not isinstance(bruto, dict):
            raise ValueError("Existe un item de kit no válido.")

        key = str(bruto.get("key") or "")
        kit_id = bruto.get("kit_id")
        try:
            cantidad = int(bruto.get("cantidad") or 0)
            kit_id = int(kit_id)
        except (TypeError, ValueError):
            raise ValueError("Kit o cantidad no válidos.")

        if cantidad <= 0:
            raise ValueError("La cantidad de kits debe ser mayor a cero.")

        kit = (
            Kit.objects
            .filter(id=kit_id, activo=True)
            .select_related("tipo_producto")
            .prefetch_related("componentes__producto")
            .first()
        )
        if not kit:
            raise ValueError("No se encontró uno de los kits seleccionados.")

        componentes = []

        if kit.modalidad == "FIJO":
            componentes_fijos = list(kit.componentes.all())
            if not componentes_fijos:
                raise ValueError(f"El kit {kit.nombre} no tiene componentes.")

            componentes = [
                {
                    "producto": componente.producto,
                    "cantidad": componente.cantidad * cantidad,
                }
                for componente in componentes_fijos
            ]
        else:
            seleccion = bruto.get("productos") or []
            if not isinstance(seleccion, list):
                raise ValueError("La selección del kit no es válida.")

            try:
                ids = [int(producto_id) for producto_id in seleccion]
            except (TypeError, ValueError):
                raise ValueError("La selección del kit contiene productos inválidos.")

            if len(ids) != int(kit.cantidad_productos or 0):
                raise ValueError(
                    f"Completá los {kit.cantidad_productos} productos de {kit.nombre}."
                )

            productos = {
                producto.id: producto
                for producto in Producto.objects.filter(
                    id__in=set(ids),
                    activo=True,
                    tipo=kit.tipo_producto,
                )
            }
            if len(productos) != len(set(ids)):
                raise ValueError(
                    f"Hay productos inválidos en la selección de {kit.nombre}."
                )

            seleccion_productos = [
                productos[producto_id]
                for producto_id in ids
            ]
            conteo = Counter(ids)
            componentes = [
                {
                    "producto": productos[producto_id],
                    "cantidad": veces * cantidad,
                }
                for producto_id, veces in conteo.items()
            ]

        precio_unitario_lista = _decimal(kit.precio)
        if kit.modalidad == "LIBRE_CATEGORIA":
            precio_unitario_lista = KitEngine.precio_unitario(
                kit,
                productos=seleccion_productos,
            )

        items.append(
            {
                "key": key,
                "kit": kit,
                "cantidad": cantidad,
                "precio_unitario_lista": precio_unitario_lista,
                "componentes": componentes,
            }
        )

    return items


def resumen_json(resumen):
    return {
        "elegible": bool(resumen["elegible"]),
        "cantidad_minima_kits": resumen["cantidad_minima_kits"],
        "total_kits": resumen["total_kits"],
        "total_piezas": resumen["total_piezas"],
        "precio_lista_total": float(resumen["precio_lista_total"]),
        "costo_total": float(resumen["costo_total"]),
        "margen_tope_ponderado": float(resumen["margen_tope_ponderado"]),
        "margen_objetivo": float(resumen["margen_objetivo"]),
        "margen_minimo": float(resumen["margen_minimo"]),
        "precio_referencia_conservador_total": float(
            resumen["precio_referencia_conservador_total"]
        ),
        "precio_objetivo_tecnico_total": float(
            resumen["precio_objetivo_tecnico_total"]
        ),
        "descuento_referencia_porcentaje": float(
            resumen["descuento_referencia_porcentaje"]
        ),
        "descuento_maximo_comercial": float(
            resumen["descuento_maximo_comercial"]
        ),
        "descuento_equilibrado_porcentaje": float(
            resumen["descuento_equilibrado_porcentaje"]
        ),
        "ajustado_por_precio_real": bool(resumen["ajustado_por_precio_real"]),
        "precio_objetivo_total": float(resumen["precio_objetivo_total"]),
        "precio_final_total": float(resumen["precio_final_total"]),
        "ahorro": float(resumen["ahorro"]),
        "descuento_porcentaje": float(resumen["descuento_porcentaje"]),
        "margen_real": float(resumen["margen_real"]),
        "limitado_por_margen": bool(resumen["limitado_por_margen"]),
        "lineas": [
            {
                "key": linea["key"],
                "kit_id": linea["kit"].id,
                "kit_nombre": linea["kit"].nombre,
                "cantidad": linea["cantidad_kits"],
                "piezas": linea["piezas"],
                "precio_unitario_lista": float(linea["precio_unitario_lista"]),
                "precio_unitario_final": float(linea["precio_unitario_final"]),
                "precio_lista_total": float(linea["precio_lista_total"]),
                "precio_final_total": float(linea["precio_final_total"]),
                "precio_referencia_conservador_unitario": float(
                    linea["precio_referencia_conservador_unitario"]
                ),
                "premium_mercado_porcentaje": float(
                    linea["premium_mercado_porcentaje"]
                ),
                "ahorro": float(linea["ahorro"]),
                "descuento_porcentaje": float(linea["descuento_porcentaje"]),
            }
            for linea in resumen["lineas"]
        ],
    }
