from django.db import models

from productos.models import Producto


class MovimientoStock(models.Model):

    TIPOS = [
        ("ENTRADA_PRODUCCION", "Entrada por producción"),
        ("ENTRADA_ARMADO", "Entrada por armado"),
        ("SALIDA_PEDIDO", "Salida por pedido"),
        ("SALIDA_ARMADO", "Salida por armado"),
        ("AJUSTE_POSITIVO", "Ajuste positivo"),
        ("AJUSTE_NEGATIVO", "Ajuste negativo"),
        ("DESCARTE", "Descarte"),
    ]

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="movimientos_stock"
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPOS
    )

    cantidad = models.PositiveIntegerField()

    fecha = models.DateTimeField(
        auto_now_add=True
    )

    referencia = models.CharField(
        max_length=100,
        blank=True,
        help_text="Ejemplo: PED0003"
    )

    observaciones = models.TextField(
        blank=True
    )

    @property
    def cantidad_con_signo(self):

        if self.tipo in [
            "ENTRADA_PRODUCCION",
            "ENTRADA_ARMADO",
            "AJUSTE_POSITIVO",
        ]:
            return self.cantidad

        return -self.cantidad

    def __str__(self):
        return (
            f"{self.producto.codigo} - "
            f"{self.get_tipo_display()} - "
            f"{self.cantidad_con_signo}"
        )
