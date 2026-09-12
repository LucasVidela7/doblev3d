from datetime import timedelta

from django.db import models

from pedidos.models import Pedido
from productos.models import Producto


class Produccion(models.Model):

    DESTINOS = [
        ("STOCK", "Stock"),
        ("PEDIDO", "Pedido"),
    ]

    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("IMPRIMIENDO", "Imprimiendo"),
        ("LISTO", "Listo"),
        ("CANCELADO", "Cancelado"),
    ]

    fecha = models.DateField(
        auto_now_add=True
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="producciones"
    )

    cantidad = models.PositiveIntegerField(
        default=1
    )

    destino = models.CharField(
        max_length=20,
        choices=DESTINOS,
        default="STOCK"
    )

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="producciones"
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE"
    )

    inicio_impresion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Inicio de impresión"
    )

    tiempo_impresion_minutos = models.PositiveIntegerField(
        default=0,
        verbose_name="Tiempo de impresión"
    )

    ingresado_stock = models.BooleanField(
        default=False
    )

    observaciones = models.TextField(
        blank=True
    )

    @property
    def codigo(self):
        if self.id:
            return f"PR{self.id:04d}"

        return "NUEVO"

    @property
    def fin_estimado(self):

        if (
            not self.inicio_impresion
            or not self.tiempo_impresion_minutos
        ):
            return None

        return (
            self.inicio_impresion
            + timedelta(
                minutes=self.tiempo_impresion_minutos
            )
        )

    @property
    def tiempo_impresion_formateado(self):

        if not self.tiempo_impresion_minutos:
            return "—"

        horas = self.tiempo_impresion_minutos // 60
        minutos = self.tiempo_impresion_minutos % 60

        if horas and minutos:
            return f"{horas} h {minutos} min"

        if horas:
            return f"{horas} h"

        return f"{minutos} min"

    def __str__(self):

        return (
            f"{self.codigo} - "
            f"{self.producto.nombre} - "
            f"x{self.cantidad}"
        )