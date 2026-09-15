from datetime import timedelta
from decimal import Decimal

from django.db import models

from pedidos.models import Pedido
from productos.models import Producto


class Impresora(models.Model):
    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    activa = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.nombre

    class Meta:
        ordering = ["nombre"]


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

    fecha = models.DateTimeField(
        auto_now_add=True,
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="producciones",
    )

    cantidad = models.PositiveIntegerField(
        default=1,
    )

    destino = models.CharField(
        max_length=20,
        choices=DESTINOS,
        default="STOCK",
    )

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="producciones",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE",
    )

    impresora = models.ForeignKey(
        Impresora,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="producciones",
    )

    inicio_impresion = models.DateTimeField(
        null=True,
        blank=True,
    )

    tiempo_impresion_minutos = models.PositiveIntegerField(
        default=0,
    )

    ingresado_stock = models.BooleanField(
        default=False,
    )

    observaciones = models.TextField(
        blank=True,
    )

    @property
    def codigo(self):
        return (
            f"PRD{self.id:04d}"
            if self.id
            else "NUEVO"
        )

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
    def peso_total_gramos(self):
        peso_unitario = Decimal(
            str(
                getattr(
                    self.producto,
                    "peso_gramos",
                    0,
                )
                or 0
            )
        )

        return (
            peso_unitario
            * Decimal(int(self.cantidad or 0))
        )

    @property
    def peso_total_formateado(self):
        total = self.peso_total_gramos

        if total >= Decimal("1000"):
            valor = total / Decimal("1000")
            texto = f"{valor:.2f}".rstrip("0").rstrip(".")
            return f"{texto} kg"

        texto = f"{total:.1f}".rstrip("0").rstrip(".")
        return f"{texto or '0'} g"

    @property
    def tiempo_impresion_formateado(self):
        total = int(
            self.tiempo_impresion_minutos or 0
        )

        if total <= 0:
            return f"⚖ {self.peso_total_formateado}"

        horas = total // 60
        minutos = total % 60

        if horas and minutos:
            duracion = f"{horas} h {minutos} min"
        elif horas:
            duracion = f"{horas} h"
        else:
            duracion = f"{minutos} min"

        return (
            f"{duracion} · "
            f"⚖ {self.peso_total_formateado}"
        )

    def __str__(self):
        return (
            f"{self.codigo} - "
            f"{self.producto.nombre} x{self.cantidad}"
        )
