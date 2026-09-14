from collections import defaultdict

from django.shortcuts import render

from productos.models import Producto
from produccion.models import Produccion

from .models import Pedido


def _nuevo_item(producto, es_pieza=False):
    return {
        "producto": producto,
        "cantidad_pedida": 0,
        "cantidad_normal": 0,
        "cantidad_personalizada": 0,
        "stock": 0,
        "a_imprimir": 0,
        "en_produccion": 0,
        "falta_iniciar": 0,
        "impresoras": [],
        "es_pieza": es_pieza,
        "origenes": set(),
    }


def _agregar_fabricacion(
    agrupados,
    producto,
    cantidad_normal,
    cantidad_personalizada,
    origen=None,
):
    """
    Convierte demanda comercial en unidades físicas a imprimir.

    - SIMPLE: se imprime el mismo producto.
    - COMPUESTO: se expande a sus piezas x cantidad.

    El stock de piezas internas NO se descuenta todavía: el stock que
    cubre pedidos sigue siendo el stock del producto comercial terminado.
    """
    cantidad_normal = max(int(cantidad_normal or 0), 0)
    cantidad_personalizada = max(int(cantidad_personalizada or 0), 0)

    if cantidad_normal <= 0 and cantidad_personalizada <= 0:
        return

    if producto.tipo_fabricacion == "COMPUESTO":
        for relacion in producto.componentes.select_related("componente").all():
            pieza = relacion.componente
            multiplicador = int(relacion.cantidad or 0)

            if multiplicador <= 0 or not pieza.requiere_impresion:
                continue

            item = agrupados.get(pieza.id)
            if item is None:
                item = _nuevo_item(pieza, es_pieza=True)
                agrupados[pieza.id] = item

            normal_piezas = cantidad_normal * multiplicador
            personalizadas_piezas = cantidad_personalizada * multiplicador

            item["cantidad_normal"] += normal_piezas
            item["cantidad_personalizada"] += personalizadas_piezas
            item["cantidad_pedida"] += normal_piezas + personalizadas_piezas
            item["a_imprimir"] += normal_piezas + personalizadas_piezas

            if origen:
                item["origenes"].add(origen)

        return

    item = agrupados.get(producto.id)
    if item is None:
        item = _nuevo_item(producto, es_pieza=False)
        agrupados[producto.id] = item

    item["cantidad_normal"] += cantidad_normal
    item["cantidad_personalizada"] += cantidad_personalizada
    item["cantidad_pedida"] += cantidad_normal + cantidad_personalizada
    item["a_imprimir"] += cantidad_normal + cantidad_personalizada

    if origen:
        item["origenes"].add(origen)


def impresiones_por_producto(request):
    """
    Vista física de lo que realmente hay que imprimir.

    Para productos compuestos no muestra el producto comercial como una
    impresión única: descuenta primero el stock terminado y luego expande
    la necesidad restante en sus piezas, respetando la cantidad definida
    en ProductoComponente.
    """
    pedidos = (
        Pedido.objects
        .exclude(estado__in=["ENTREGADO", "CANCELADO"])
        .prefetch_related(
            "detalles__producto__componentes__componente",
            "detalles__kit",
            "detalles__productos_kit__producto__componentes__componente",
            "estados_impresion",
        )
        .order_by("fecha_entrega", "id")
    )

    # Primero reunimos demanda por PRODUCTO COMERCIAL. El stock se aplica
    # acá, antes de convertir compuestos en piezas físicas.
    demanda_comercial = defaultdict(
        lambda: {
            "producto": None,
            "cantidad_normal": 0,
            "cantidad_personalizada": 0,
        }
    )

    for pedido in pedidos:
        productos_normales_listos = {
            estado.producto_id
            for estado in pedido.estados_impresion.all()
            if estado.listo
        }

        for detalle in pedido.detalles.all():
            if detalle.estado in ["CANCELADO", "ENTREGADO"]:
                continue

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.estado == "LISTO":
                    continue

                item = demanda_comercial[detalle.producto_id]
                item["producto"] = detalle.producto
                item["cantidad_personalizada"] += detalle.cantidad
                continue

            if (
                detalle.tipo_item == "PRODUCTO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.producto_id in productos_normales_listos:
                    continue

                item = demanda_comercial[detalle.producto_id]
                item["producto"] = detalle.producto
                item["cantidad_normal"] += detalle.cantidad
                continue

            if detalle.tipo_item == "KIT" and detalle.kit:
                for componente_kit in detalle.productos_kit.all():
                    producto = componente_kit.producto

                    if not producto.requiere_impresion:
                        continue

                    if producto.id in productos_normales_listos:
                        continue

                    item = demanda_comercial[producto.id]
                    item["producto"] = producto
                    item["cantidad_normal"] += componente_kit.cantidad

    # Convertimos demanda comercial en unidades físicas imprimibles.
    productos_agrupados = {}

    for demanda in demanda_comercial.values():
        producto = demanda["producto"]
        if not producto:
            continue

        cantidad_normal = demanda["cantidad_normal"]
        cantidad_personalizada = demanda["cantidad_personalizada"]

        # El stock existente corresponde al producto terminado.
        falta_normal = max(cantidad_normal - int(producto.stock or 0), 0)

        _agregar_fabricacion(
            productos_agrupados,
            producto,
            falta_normal,
            cantidad_personalizada,
            origen=producto.nombre,
        )

        # Para productos simples mantenemos la lectura histórica de STOCK y
        # PEDIDO: la columna pedido muestra la demanda comercial completa y
        # A IMPRIMIR solamente lo que falta después del stock.
        if producto.tipo_fabricacion == "SIMPLE":
            item = productos_agrupados.get(producto.id)
            if item:
                item["cantidad_pedida"] = cantidad_normal + cantidad_personalizada
                item["cantidad_normal"] = cantidad_normal
                item["stock"] = int(producto.stock or 0)
                item["a_imprimir"] = falta_normal + cantidad_personalizada

    # Producciones ya iniciadas se descuentan sobre la unidad FÍSICA.
    producciones_en_curso = (
        Produccion.objects
        .filter(estado="IMPRIMIENDO")
        .select_related("producto", "impresora")
        .order_by("producto_id", "id")
    )

    en_curso_por_producto = defaultdict(
        lambda: {"cantidad": 0, "impresoras": []}
    )

    for produccion in producciones_en_curso:
        item_curso = en_curso_por_producto[produccion.producto_id]
        item_curso["cantidad"] += produccion.cantidad

        if produccion.impresora:
            item_curso["impresoras"].append(
                f"{produccion.impresora.nombre} · {produccion.cantidad}"
            )

    lista_productos = []

    for item in productos_agrupados.values():
        producto = item["producto"]
        produciendo = en_curso_por_producto.get(
            producto.id,
            {"cantidad": 0, "impresoras": []},
        )

        item["en_produccion"] = produciendo["cantidad"]
        item["impresoras"] = produciendo["impresoras"]
        item["falta_iniciar"] = max(
            item["a_imprimir"] - item["en_produccion"],
            0,
        )
        item["origenes"] = sorted(item["origenes"])

        falta_iniciar = item["falta_iniciar"]
        en_produccion = item["en_produccion"]
        a_imprimir = item["a_imprimir"]

        if falta_iniciar >= 6:
            item["prioridad"] = "ALTA"
            item["prioridad_clase"] = "prioridad-alta"
        elif falta_iniciar >= 3:
            item["prioridad"] = "MEDIA"
            item["prioridad_clase"] = "prioridad-media"
        elif falta_iniciar >= 1:
            item["prioridad"] = "BAJA"
            item["prioridad_clase"] = "prioridad-baja"
        elif en_produccion > 0 and a_imprimir > 0:
            item["prioridad"] = "EN CURSO"
            item["prioridad_clase"] = "prioridad-curso"
        else:
            item["prioridad"] = "SIN NECESIDAD"
            item["prioridad_clase"] = "prioridad-cero"

        lista_productos.append(item)

    lista_productos.sort(
        key=lambda item: (
            -item["falta_iniciar"],
            -item["en_produccion"],
            0 if item["es_pieza"] else 1,
            item["producto"].nombre.lower(),
        )
    )

    return render(
        request,
        "pedidos/impresiones_por_producto.html",
        {"productos": lista_productos},
    )
