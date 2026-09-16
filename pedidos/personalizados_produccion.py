import re
from collections import defaultdict

from django.db import transaction

from produccion.models import Produccion

from .models import DetallePedido, EstadoImpresionPedido, Pedido


MARCA_PERSONALIZADO = "PERSONALIZADO:"
PATRON_PERSONALIZADO = re.compile(r"PERSONALIZADO:(\d+)")


def detalle_id_desde_observaciones(observaciones):
    """Extrae el DetallePedido personalizado vinculado a una producción."""
    coincidencia = PATRON_PERSONALIZADO.search(observaciones or "")
    if not coincidencia:
        return None

    try:
        return int(coincidencia.group(1))
    except (TypeError, ValueError):
        return None


def requerimientos_fisicos_personalizado(detalle):
    """
    Devuelve {producto_fisico_id: cantidad} para completar un personalizado.

    Un producto SIMPLE se imprime a sí mismo. Un producto COMPUESTO se expande
    a sus piezas de fabricación, respetando la cantidad pedida y la cantidad
    de cada componente.
    """
    producto = detalle.producto
    if not producto or not producto.requiere_impresion:
        return {}

    cantidad_detalle = max(int(detalle.cantidad or 0), 0)
    if cantidad_detalle <= 0:
        return {}

    if producto.tipo_fabricacion != "COMPUESTO":
        return {producto.id: cantidad_detalle}

    requerimientos = defaultdict(int)
    for relacion in producto.componentes.select_related("componente").all():
        componente = relacion.componente
        if not componente.requiere_impresion:
            continue

        cantidad_componente = max(int(relacion.cantidad or 0), 0)
        if cantidad_componente <= 0:
            continue

        requerimientos[componente.id] += (
            cantidad_detalle * cantidad_componente
        )

    return dict(requerimientos)


def cantidades_finalizadas_personalizado(detalle):
    """Suma únicamente producción LISTO asociada a ese personalizado."""
    marca = f"{MARCA_PERSONALIZADO}{detalle.id}"
    cantidades = defaultdict(int)

    producciones = (
        Produccion.objects
        .filter(
            estado="LISTO",
            observaciones__contains=marca,
        )
        .values_list("producto_id", "cantidad")
    )

    for producto_id, cantidad in producciones:
        cantidades[producto_id] += int(cantidad or 0)

    return dict(cantidades)


def personalizado_esta_completo(detalle):
    requerimientos = requerimientos_fisicos_personalizado(detalle)
    if not requerimientos:
        return False

    finalizadas = cantidades_finalizadas_personalizado(detalle)
    return all(
        int(finalizadas.get(producto_id, 0)) >= int(cantidad_necesaria)
        for producto_id, cantidad_necesaria in requerimientos.items()
    )


def actualizar_estado_general_pedido(pedido):
    """
    Recalcula el estado del pedido desde la demanda real.

    Para productos y kits usa EstadoImpresionPedido por producto físico.
    Para personalizados usa el estado del DetallePedido. No crea estados nuevos
    ni toca stock; únicamente refleja PENDIENTE / PREPARANDO / LISTO.
    """
    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        return pedido.estado

    detalles = list(
        pedido.detalles
        .exclude(estado="CANCELADO")
        .select_related("producto", "kit")
        .prefetch_related("productos_kit__producto")
    )

    productos_normales = set()
    personalizados_total = 0
    personalizados_listos = 0

    for detalle in detalles:
        if detalle.tipo_item == "PERSONALIZADO":
            if detalle.producto and detalle.producto.requiere_impresion:
                personalizados_total += 1
                if detalle.estado == "LISTO":
                    personalizados_listos += 1
            continue

        if (
            detalle.tipo_item == "PRODUCTO"
            and detalle.producto
            and detalle.producto.requiere_impresion
        ):
            productos_normales.add(detalle.producto_id)
            continue

        if detalle.tipo_item == "KIT":
            for componente in detalle.productos_kit.all():
                if componente.producto.requiere_impresion:
                    productos_normales.add(componente.producto_id)

    estados_listos = set(
        EstadoImpresionPedido.objects
        .filter(
            pedido=pedido,
            producto_id__in=productos_normales,
            listo=True,
        )
        .values_list("producto_id", flat=True)
    )

    cantidad_total = len(productos_normales) + personalizados_total
    cantidad_lista = len(estados_listos) + personalizados_listos

    if cantidad_total > 0 and cantidad_lista == cantidad_total:
        nuevo_estado = "LISTO"
    elif cantidad_lista > 0:
        nuevo_estado = "PREPARANDO"
    else:
        nuevo_estado = "PENDIENTE"

    if pedido.estado != nuevo_estado:
        Pedido.objects.filter(pk=pedido.pk).update(estado=nuevo_estado)
        pedido.estado = nuevo_estado

    return nuevo_estado


@transaction.atomic
def sincronizar_detalle_personalizado(detalle_id):
    """
    Sincroniza un personalizado con las producciones que llevan su marca.

    LISTO significa que todas sus unidades físicas ya tienen producción LISTO.
    Si una producción se revierte/cancela y deja de cubrir la necesidad, vuelve
    a PENDIENTE. Los pedidos entregados/cancelados se conservan históricos.
    """
    detalle = (
        DetallePedido.objects
        .select_for_update()
        .select_related("pedido", "producto")
        .prefetch_related("producto__componentes__componente")
        .filter(
            id=detalle_id,
            tipo_item="PERSONALIZADO",
        )
        .first()
    )

    if not detalle:
        return None

    pedido = Pedido.objects.select_for_update().get(pk=detalle.pedido_id)
    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        return detalle.estado

    nuevo_estado = (
        "LISTO"
        if personalizado_esta_completo(detalle)
        else "PENDIENTE"
    )

    if detalle.estado != nuevo_estado:
        DetallePedido.objects.filter(pk=detalle.pk).update(estado=nuevo_estado)
        detalle.estado = nuevo_estado

    actualizar_estado_general_pedido(pedido)
    return nuevo_estado


def sincronizar_personalizados_pendientes():
    """
    Repara pedidos históricos que ya tenían producción LISTO antes de existir
    esta sincronización. Se usa al entrar a Impresiones por producto.
    """
    ids = list(
        DetallePedido.objects
        .filter(
            tipo_item="PERSONALIZADO",
            estado="PENDIENTE",
            producto__requiere_impresion=True,
        )
        .exclude(pedido__estado__in=["ENTREGADO", "CANCELADO"])
        .values_list("id", flat=True)
    )

    for detalle_id in ids:
        sincronizar_detalle_personalizado(detalle_id)
