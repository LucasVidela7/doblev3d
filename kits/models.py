from django.db import models
from productos.models import TipoProducto


class Kit(models.Model):

    nombre = models.CharField(
        max_length=150,
        unique=True
    )

    tipo_producto = models.ForeignKey(
        TipoProducto,
        on_delete=models.PROTECT,
        related_name="kits"
    )

    cantidad_productos = models.PositiveIntegerField(
        default=1,
        verbose_name="Cantidad de productos"
    )

    precio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    activo = models.BooleanField(
        default=True
    )

    @property
    def codigo(self):
        return f"K{self.id:04d}" if self.id else "NUEVO"

    def __str__(self):
        if self.id:
            return f"{self.codigo} - {self.nombre}"
        return self.nombre