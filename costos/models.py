from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class ConfiguracionCostos(models.Model):
    nombre = models.CharField(
        max_length=100,
        default="Configuración general"
    )

    coste_plastico_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Coste plástico por kg"
    )

    tasa_fallos = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        verbose_name="Tasa de fallos (%)"
    )

    coste_luz_hora = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Coste luz por hora"
    )

    coste_amortizacion_hora = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Coste amortización por hora"
    )

    fecha_desde = models.DateField()

    activa = models.BooleanField(default=True)

    def tramo_filamento_para_gramos(self, total_gramos):
        """Devuelve el tramo de volumen aplicable al peso total de la venta."""
        total_gramos = max(
            Decimal(str(total_gramos or 0)),
            Decimal("0"),
        )

        if not self.pk or total_gramos <= 0:
            return None

        return (
            self.tramos_filamento
            .filter(
                activo=True,
                desde_gramos__lte=total_gramos,
                coste_plastico_kg__gt=0,
            )
            .order_by("-desde_gramos")
            .first()
        )

    def precio_filamento_para_gramos(self, total_gramos):
        """
        Precio/kg a usar para una venta según sus gramos totales.

        El coste estándar siempre funciona como techo: un tramo mal cargado
        nunca encarece el material respecto del coste normal del producto.
        """
        estandar = max(
            Decimal(str(self.coste_plastico_kg or 0)),
            Decimal("0"),
        )
        tramo = self.tramo_filamento_para_gramos(total_gramos)

        if not tramo:
            return estandar

        precio_tramo = max(
            Decimal(str(tramo.coste_plastico_kg or 0)),
            Decimal("0"),
        )

        if estandar > 0:
            return min(estandar, precio_tramo)
        return precio_tramo

    def __str__(self):
        return f"{self.nombre} - {self.fecha_desde}"


class TramoCostoFilamento(models.Model):
    configuracion = models.ForeignKey(
        ConfiguracionCostos,
        on_delete=models.CASCADE,
        related_name="tramos_filamento",
    )
    desde_gramos = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Desde gramos totales",
        help_text=(
            "Peso total de filamento de la venta a partir del cual se usa "
            "este precio por kg. Ejemplo: 1000 para 1 kg."
        ),
    )
    coste_plastico_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Coste plástico por kg",
        help_text=(
            "Precio de compra habitual que podés conseguir para este volumen."
        ),
    )
    activo = models.BooleanField(default=True)

    def clean(self):
        errores = {}

        if self.desde_gramos is not None and self.desde_gramos <= 0:
            errores["desde_gramos"] = (
                "El tramo debe empezar en un peso mayor a cero."
            )

        if self.coste_plastico_kg is not None and self.coste_plastico_kg <= 0:
            errores["coste_plastico_kg"] = (
                "El precio por kg debe ser mayor a cero."
            )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        kg = Decimal(str(self.desde_gramos or 0)) / Decimal("1000")
        return (
            f"Desde {kg.normalize()} kg · "
            f"${self.coste_plastico_kg}/kg"
        )

    class Meta:
        ordering = ["desde_gramos"]
        constraints = [
            models.UniqueConstraint(
                fields=["configuracion", "desde_gramos"],
                name="costo_filamento_tramo_unico",
            )
        ]
