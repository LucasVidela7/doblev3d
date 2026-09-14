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

    @property
    def total_pagado(self):
        return sum(
            (pago.monto for pago in self.pagos.all()),
            Decimal("0")
        )

    @property
    def saldo_pendiente(self):
        saldo = self.total - self.total_pagado
        return max(saldo, Decimal("0"))

    @property
    def estado_pago(self):
        pagado = self.total_pagado
        total = self.total

        if pagado <= 0:
            return "SIN_PAGAR"
        if pagado < total:
            return "PARCIAL"
        return "PAGADO"

    @property
    def estado_pago_display(self):
        return {
            "SIN_PAGAR": "Sin pagar",
            "PARCIAL": "Parcial",
            "PAGADO": "Pagado",
        }[self.estado_pago]

    def __str__(self):
        if self.id:
            return f"{self.codigo} - {self.cliente.nombre}"
        return f"Pedido - {self.cliente.nombre}"


class DetallePedido(models.Model):
    TIPOS_ITEM = [
        ("PRODUCTO", "Producto"),
        ("KIT", "Kit"),
        ("PERSONALIZADO", "Personalizado"),
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

    # Snapshot del costo por unidad al momento de la venta.
    # NULL = detalle anterior al módulo de rentabilidad.
    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
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

    color_personalizacion = models.CharField(
        max_length=100,
        blank=True
    )

    precio_total_personalizado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    @property
    def subtotal(self):
        if (
            self.tipo_item == "PERSONALIZADO"
            and self.precio_total_personalizado is not None
        ):
            return self.precio_total_personalizado

        return self.precio_unitario * self.cantidad

    @property
    def costo_total_historico(self):
        if self.costo_unitario is None:
            return None
        return self.costo_unitario * self.cantidad

    @property
    def ganancia_bruta_historica(self):
        costo = self.costo_total_historico
        if costo is None:
            return None
        return self.subtotal - costo

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

        if self.tipo_item == "PERSONALIZADO" and self.producto:
            return (
                f"{self.pedido.codigo} - "
                f"{self.producto.nombre} personalizado"
            )

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


class Pago(models.Model):
    MEDIOS = [
        ("EFECTIVO", "Efectivo"),
        ("TRANSFERENCIA", "Transferencia"),
        ("MERCADO_PAGO", "Mercado Pago"),
        ("OTRO", "Otro"),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        related_name="pagos"
    )

    fecha = models.DateTimeField(auto_now_add=True)

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    medio = models.CharField(
        max_length=30,
        choices=MEDIOS
    )

    observaciones = models.CharField(
        max_length=250,
        blank=True
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return (
            f"{self.pedido.codigo} - "
            f"{self.get_medio_display()} - "
            f"${self.monto}"
        )
