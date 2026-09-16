from django.db.models.signals import post_save
from django.dispatch import receiver

from .kits_volumen import aplicar_precio_volumen_pedido
from .models import DetalleKitProducto


@receiver(post_save, sender=DetalleKitProducto)
def recalcular_precio_volumen_kits(sender, instance, **kwargs):
    """
    Cada vez que termina de guardarse un componente de kit, recalculamos
    el conjunto completo de kits del pedido.

    La señal es sincrónica y corre dentro de la misma transacción que Nuevo
    Pedido / Editar Pedido, por lo que el precio persistido queda protegido
    por backend y no depende de lo que envíe el navegador.
    """
    detalle = instance.detalle
    if not detalle.pedido_id:
        return

    aplicar_precio_volumen_pedido(detalle.pedido)
