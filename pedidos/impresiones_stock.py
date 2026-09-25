from .impresiones_compuestas import (
    obtener_impresiones_por_producto as _obtener_impresiones_por_producto_base,
)


def _actualizar_prioridad(item):
    falta_iniciar = int(item.get("falta_iniciar") or 0)
    en_produccion = int(item.get("en_produccion") or 0)
    en_control = int(item.get("en_control") or 0)
    planificadas = int(item.get("planificadas") or 0)
    a_imprimir = int(item.get("a_imprimir") or 0)

    if falta_iniciar >= 6:
        item["prioridad"] = "ALTA"
        item["prioridad_clase"] = "prioridad-alta"
    elif falta_iniciar >= 3:
        item["prioridad"] = "MEDIA"
        item["prioridad_clase"] = "prioridad-media"
    elif falta_iniciar >= 1:
        item["prioridad"] = "BAJA"
        item["prioridad_clase"] = "prioridad-baja"
    elif (
        en_produccion > 0
        or en_control > 0
        or planificadas > 0
    ) and a_imprimir > 0:
        item["prioridad"] = "EN CURSO"
        item["prioridad_clase"] = "prioridad-curso"
    else:
        item["prioridad"] = "SIN NECESIDAD"
        item["prioridad_clase"] = "prioridad-cero"


def aplicar_stock_real(productos):
    """
    Normaliza el stock de cada unidad física mostrada en Impresiones por producto.

    La vista histórica ya descuenta correctamente el stock de un producto SIMPLE,
    pero al expandir un COMPUESTO a sus piezas deja el stock de cada pieza en cero.
    Acá se vuelve a tomar el stock real del Producto físico y se recalculan las
    cantidades estándar pendientes.

    El stock sólo cubre demanda estándar. Las personalizaciones continúan siendo
    fabricación específica y no consumen stock genérico.
    """
    for item in productos:
        producto = item.get("producto")
        if producto is None:
            continue

        stock = max(int(producto.stock or 0), 0)
        cantidad_normal = max(int(item.get("cantidad_normal") or 0), 0)
        cantidad_personalizada = max(
            int(item.get("cantidad_personalizada") or 0),
            0,
        )
        planificadas = max(int(item.get("planificadas") or 0), 0)
        en_produccion = max(int(item.get("en_produccion") or 0), 0)
        en_control = max(int(item.get("en_control") or 0), 0)

        necesidad_normal = max(cantidad_normal - stock, 0)

        personalizadas_planificadas = sum(
            max(int(personalizacion.get("planificadas") or 0), 0)
            for personalizacion in item.get("personalizaciones", [])
        )
        personalizadas_imprimiendo = sum(
            max(int(personalizacion.get("imprimiendo") or 0), 0)
            for personalizacion in item.get("personalizaciones", [])
        )
        personalizadas_control = sum(
            max(int(personalizacion.get("control") or 0), 0)
            for personalizacion in item.get("personalizaciones", [])
        )

        planificadas_estandar = max(
            planificadas - personalizadas_planificadas,
            0,
        )
        imprimiendo_estandar = max(
            en_produccion - personalizadas_imprimiendo,
            0,
        )
        control_estandar = max(
            en_control - personalizadas_control,
            0,
        )

        item["stock"] = stock
        item["necesidad_normal_impresion"] = necesidad_normal
        item["a_imprimir"] = necesidad_normal + cantidad_personalizada
        item["falta_normal_planificar"] = max(
            necesidad_normal
            - planificadas_estandar
            - imprimiendo_estandar
            - control_estandar,
            0,
        )
        item["falta_iniciar"] = max(
            item["a_imprimir"]
            - planificadas
            - en_produccion
            - en_control,
            0,
        )

        _actualizar_prioridad(item)

    productos.sort(
        key=lambda item: (
            -int(item.get("falta_iniciar") or 0),
            -int(item.get("en_produccion") or 0),
            -int(item.get("planificadas") or 0),
            0 if item.get("es_pieza") else 1,
            item["producto"].nombre.lower(),
        )
    )

    return productos


def obtener_impresiones_por_producto():
    return aplicar_stock_real(_obtener_impresiones_por_producto_base())
