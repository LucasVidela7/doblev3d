from productos.miniaturas import asignar_miniaturas_productos


def _producto_representativo(item):
    producto = getattr(item, "producto", None)
    if producto:
        return producto

    productos_kit = getattr(item, "productos_kit", None)
    if productos_kit is not None:
        try:
            componentes = list(productos_kit.all())
        except Exception:
            componentes = []
        for componente in componentes:
            producto = getattr(componente, "producto", None)
            if producto:
                return producto

    kit = getattr(item, "kit", None)
    if kit is not None:
        componentes = getattr(kit, "componentes", None)
        if componentes is not None:
            try:
                componentes = list(componentes.all())
            except Exception:
                componentes = []
            for componente in componentes:
                producto = getattr(componente, "producto", None)
                if producto:
                    return producto

    return None


def asignar_miniaturas_items(items):
    """Asigna una miniatura representativa a ítems de pedido/presupuesto/web."""
    items = list(items or [])
    productos = []

    for item in items:
        producto = _producto_representativo(item)
        item.producto_representativo = producto
        if producto:
            productos.append(producto)

    asignar_miniaturas_productos(productos)

    for item in items:
        producto = getattr(
            item,
            "producto_representativo",
            None,
        )
        item.imagen_pedido_url = (
            getattr(
                producto,
                "imagen_produccion_url",
                "",
            )
            if producto
            else ""
        )

    return items


def asignar_miniatura_resumen(objetos, relacion):
    """Asigna al padre la miniatura del primer ítem de una relación prefetched."""
    objetos = list(objetos or [])
    items = []

    for objeto in objetos:
        gestor = getattr(objeto, relacion, None)
        if gestor is None:
            objeto.imagen_resumen_url = ""
            continue

        try:
            relacionados = list(gestor.all())
        except Exception:
            relacionados = []

        objeto._items_con_miniatura = relacionados
        items.extend(relacionados)

    asignar_miniaturas_items(items)

    for objeto in objetos:
        relacionados = getattr(
            objeto,
            "_items_con_miniatura",
            [],
        )
        objeto.imagen_resumen_url = next(
            (
                getattr(item, "imagen_pedido_url", "")
                for item in relacionados
                if getattr(item, "imagen_pedido_url", "")
            ),
            "",
        )

    return objetos
