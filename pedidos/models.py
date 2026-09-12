from decimal import Decimal

from django.db import models

from clientes.models import Cliente
from productos.models import Producto
from kits.models import Kit


class Pedido(models.Model):
    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("PREPARANDO", "Preparando"),
        ("LISTO", "Listo"),
        ("ENTREGADO", "Entregado"),
        ("CANCELADO", "Cancelado"),
    ]

    fecha = models.DateField(
        auto_now_add=True
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="pedidos"
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE"
    )

    fecha_entrega = models.DateField(
        null=True,
        blank=True
    )

    observaciones = models.TextField(
        blank=True
    )

    @property
    def codigo(self):
        return f"PED{self.id:04d}" if self.id else "NUEVO"

    @property
    def total(self):
        return sum(
            (detalle.subtotal for detalle in self.detalles.all()),
            Decimal("0")
        )

    def __str__(self):
        if self.id:
            return f"{self.codigo} - {self.cliente.nombre}"
        return f"Pedido - {self.cliente.nombre}"


class DetallePedido(models.Model):
    TIPOS_ITEM = [
        ("PRODUCTO", "Producto"),
        ("KIT", "Kit"),
    ]

    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("LISTO", "Listo"),
        ("ENTREGADO", "Entregado"),
        ("CANCELADO", "Cancelado"),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="detalles"
    )

    tipo_item = models.CharField(
        max_length=20,
        choices=TIPOS_ITEM
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_pedido"
    )

    kit = models.ForeignKey(
        Kit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_pedido"
    )

    cantidad = models.PositiveIntegerField(
        default=1
    )

    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE"
    )

    personalizado = models.BooleanField(
        default=False
    )

    detalle_personalizacion = models.TextField(
        blank=True
    )

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad

    def save(self, *args, **kwargs):

        if self.precio_unitario == 0:

            if self.tipo_item == "PRODUCTO" and self.producto:
                self.precio_unitario = self.producto.subtotal

            elif self.tipo_item == "KIT" and self.kit:
                self.precio_unitario = self.kit.precio

        super().save(*args, **kwargs)

    def __str__(self):

        if self.tipo_item == "PRODUCTO" and self.producto:
            return f"{self.pedido.codigo} - {self.producto.nombre}"

        if self.tipo_item == "KIT" and self.kit:
            return f"{self.pedido.codigo} - {self.kit.nombre}"

        return self.pedido.codigo


class DetalleKitProducto(models.Model):
    detalle = models.ForeignKey(
        DetallePedido,
        on_delete=models.CASCADE,
        related_name="productos_kit"
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT
    )

    cantidad = models.PositiveIntegerField(
        default=1
    )

    def __str__(self):
        return f"{self.detalle} - {self.producto.nombre}"


class EstadoImpresionPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="estados_impresion"
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT
    )

    listo = models.BooleanField(
        default=False
    )

    stock_descontado = models.BooleanField(
        default=False
    )

    cantidad_stock_descontada = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "pedido",
                    "producto",
                ],
                name="estado_impresion_pedido_producto_unico"
            )
        ]

    def __str__(self):
        estado = "LISTO" if self.listo else "PENDIENTE"

        return (
            f"{self.pedido.codigo} - "
            f"{self.producto.nombre} - "
            f"{estado}"
        )
