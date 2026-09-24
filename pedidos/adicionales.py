from decimal import Decimal, InvalidOperation


CERO = Decimal("0")


def _decimal(valor):
    try:
        return Decimal(str(valor or 0))
    except (InvalidOperation, TypeError, ValueError):
        return CERO


def desglose_item_solicitud(item):
    """Devuelve el desglose exacto que se congeló al crear la solicitud."""
    adicional_total = max(
        _decimal(getattr(item, "adicional_unitario", 0)),
        CERO,
    )
    adicional_color = min(
        max(
            _decimal(
                getattr(
                    item,
                    "adicional_color_unitario",
                    0,
                )
            ),
            CERO,
        ),
        adicional_total,
    )
    adicional_opciones = max(
        adicional_total - adicional_color,
        CERO,
    )
    cantidad = max(int(getattr(item, "cantidad", 0) or 0), 0)
    precio_base = max(
        _decimal(
            getattr(
                item,
                "precio_base_unitario",
                0,
            )
        ),
        CERO,
    )
    precio_final = max(
        _decimal(getattr(item, "precio_unitario", 0)),
        CERO,
    )
    precio_lista = precio_base + adicional_total
    descuento = max(precio_lista - precio_final, CERO)

    return {
        "precio_base_unitario": precio_base,
        "adicional_opciones_unitario": adicional_opciones,
        "adicional_color_unitario": adicional_color,
        "adicional_total_unitario": adicional_total,
        "adicional_total_linea": (
            adicional_total * Decimal(cantidad)
        ),
        "precio_lista_unitario": precio_lista,
        "precio_final_unitario": precio_final,
        "descuento_unitario": descuento,
        "tiene_adicionales": adicional_total > 0,
        "tiene_descuento": descuento > 0,
    }


def _identidad_detalle(detalle):
    if detalle.tipo_item == "KIT":
        return ("KIT", detalle.kit_id)
    if detalle.tipo_item in {"PRODUCTO", "PERSONALIZADO"}:
        return (detalle.tipo_item, detalle.producto_id)
    return (detalle.tipo_item, None)


def _identidad_item_solicitud(item):
    if item.tipo_item == "KIT":
        return ("KIT", item.kit_id)
    return ("PRODUCTO", item.producto_id)


def _solicitud_origen(pedido):
    presupuesto = getattr(pedido, "presupuesto_origen", None)
    if not presupuesto:
        return None

    try:
        return presupuesto.solicitud_web_origen
    except Exception:
        return None


def _fuentes_por_detalle(pedido, detalles):
    """Relaciona líneas del pedido con la solicitud web original."""
    solicitud = _solicitud_origen(pedido)
    if not solicitud:
        return {}

    items = list(
        solicitud.items.all().order_by("id")
    )
    disponibles = list(enumerate(items))
    fuentes = {}

    for detalle in detalles:
        identidad = _identidad_detalle(detalle)
        encontrado = None

        for posicion, (_indice, item) in enumerate(disponibles):
            if identidad[0] == "PERSONALIZADO":
                continue
            if _identidad_item_solicitud(item) != identidad:
                continue
            encontrado = (posicion, item)
            break

        if encontrado is None:
            continue

        posicion, item = encontrado
        disponibles.pop(posicion)
        fuentes[detalle.id] = item

    return fuentes


def _desglose_desde_snapshot(detalle):
    snapshot = dict(getattr(detalle, "kit_snapshot", None) or {})

    if not snapshot:
        return None

    adicional_total = max(
        _decimal(snapshot.get("adicional_unitario")),
        CERO,
    )
    adicional_color = max(
        _decimal(snapshot.get("adicional_color_unitario")),
        CERO,
    )
    adicional_opciones = max(
        _decimal(snapshot.get("adicional_opciones_unitario")),
        CERO,
    )

    if adicional_total <= 0:
        adicional_total = adicional_opciones + adicional_color

    if adicional_total <= 0 and not getattr(
        detalle,
        "precio_kit_manual",
        False,
    ):
        precio_base = max(
            _decimal(snapshot.get("precio_base")),
            CERO,
        )
        precio_vendido = max(
            _decimal(
                snapshot.get("precio_unitario_vendido")
                or detalle.precio_unitario
            ),
            CERO,
        )
        adicional_total = max(
            precio_vendido - precio_base,
            CERO,
        )
        adicional_color = min(
            max(
                _decimal(
                    (
                        snapshot.get("seleccion_color")
                        or {}
                    ).get("adicional_unitario")
                ),
                CERO,
            ),
            adicional_total,
        )
        adicional_opciones = max(
            adicional_total - adicional_color,
            CERO,
        )

    if adicional_total <= 0:
        return None

    precio_base = max(
        _decimal(snapshot.get("precio_base")),
        CERO,
    )
    precio_lista = max(
        _decimal(snapshot.get("precio_lista_unitario")),
        precio_base + adicional_total,
    )
    precio_final = max(
        _decimal(getattr(detalle, "precio_unitario", 0)),
        CERO,
    )
    cantidad = max(int(getattr(detalle, "cantidad", 0) or 0), 0)

    return {
        "precio_base_unitario": precio_base,
        "adicional_opciones_unitario": adicional_opciones,
        "adicional_color_unitario": adicional_color,
        "adicional_total_unitario": adicional_total,
        "adicional_total_linea": (
            adicional_total * Decimal(cantidad)
        ),
        "precio_lista_unitario": precio_lista,
        "precio_final_unitario": precio_final,
        "descuento_unitario": max(
            precio_lista - precio_final,
            CERO,
        ),
        "tiene_adicionales": True,
        "tiene_descuento": precio_final < precio_lista,
    }


def enriquecer_detalles_pedido(pedido, detalles):
    """Agrega un desglose transitorio de adicionales a cada detalle."""
    detalles = list(detalles)
    fuentes = _fuentes_por_detalle(
        pedido,
        detalles,
    )

    for detalle in detalles:
        desglose = None
        fuente = fuentes.get(detalle.id)

        if fuente is not None:
            desglose = desglose_item_solicitud(fuente)
            if not desglose["tiene_adicionales"]:
                desglose = None

        if desglose is None and detalle.tipo_item == "KIT":
            desglose = _desglose_desde_snapshot(detalle)

        detalle.adicionales = desglose

    return detalles
