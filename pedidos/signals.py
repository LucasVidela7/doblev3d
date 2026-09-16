from django.db.models.signals import post_save
from django.dispatch import receiver

from produccion.models import Produccion

from .kits_volumen import aplicar_precio_volumen_pedido
from .models import DetalleKitProducto, DetallePedido
from .personalizados_produccion import (
    detalle_id_desde_observaciones,
    sincronizar_detalle_personalizado,
)


@receiver(post_save, sender=DetalleKitProducto)
def recalcular_precio_volumen_kits(sender, instance, **kwargs):
    """
    Recalcula el precio automático por volumen cuando cambia la composición
    de un kit, pero conserva cualquier precio de KIT acordado manualmente.

    Los kits con precio manual siguen contando para el volumen total de piezas
    y para decidir si el pedido califica como mayorista; lo único que se evita
    es que el cálculo automático sobrescriba el importe acordado con el cliente.
    """
    detalle = instance.detalle
    if not detalle.pedido_id:
        return

    pedido = detalle.pedido

    precios_manuales = dict(
        DetallePedido.objects.filter(
            pedido=pedido,
            tipo_item="KIT",
            precio_kit_manual=True,
        ).values_list("id", "precio_unitario")
    )

    aplicar_precio_volumen_pedido(pedido)

    # update() evita ejecutar save() y restaura exactamente los importes
    # acordados después de que el cálculo automático actualizó el conjunto.
    for detalle_id, precio_unitario in precios_manuales.items():
        DetallePedido.objects.filter(
            id=detalle_id,
            pedido=pedido,
            tipo_item="KIT",
            precio_kit_manual=True,
        ).update(precio_unitario=precio_unitario)


@receiver(post_save, sender=Produccion)
def sincronizar_personalizado_con_produccion(sender, instance, **kwargs):
    """
    Una producción asociada a un personalizado lleva la marca
    PERSONALIZADO:<detalle_id> en observaciones.

    Cada cambio de estado vuelve a comprobar la cobertura física completa. De
    esta forma, al pasar la última placa necesaria a LISTO el detalle también
    queda LISTO y desaparece de la necesidad de planificación. Si se revierte o
    cancela una placa finalizada, la necesidad puede volver a PENDIENTE.
    """
    detalle_id = detalle_id_desde_observaciones(instance.observaciones)
    if detalle_id:
        sincronizar_detalle_personalizado(detalle_id)
