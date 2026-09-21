from decimal import Decimal

from django.core.cache import cache
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

    coste_plastico_kg_cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Coste plástico por kg para cantidad",
        help_text=(
            "Se usa desde 5 unidades en la calculadora y para kits. "
            "Si queda en 0, se usa el coste estándar."
        ),
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

    @property
    def coste_plastico_kg_cantidad_efectivo(self):
        """Costo económico usable, con retorno seguro al precio estándar."""
        estandar = max(
            Decimal(str(self.coste_plastico_kg or 0)),
            Decimal("0"),
        )
        cantidad = max(
            Decimal(str(self.coste_plastico_kg_cantidad or 0)),
            Decimal("0"),
        )

        if cantidad <= 0:
            return estandar

        # Una configuración mayorista cargada por error nunca debe encarecer
        # el producto respecto del costo conservador estándar.
        if estandar > 0:
            return min(estandar, cantidad)

        return cantidad

    def __str__(self):
        return f"{self.nombre} - {self.fecha_desde}"

    def save(self, *args, **kwargs):
        resultado = super().save(*args, **kwargs)
        cache.delete("dv-configuracion-costos-activa-v1")
        cache.delete("dv-catalog-rotator-payload-v1")
        return resultado

    def delete(self, *args, **kwargs):
        resultado = super().delete(*args, **kwargs)
        cache.delete("dv-configuracion-costos-activa-v1")
        cache.delete("dv-catalog-rotator-payload-v1")
        return resultado