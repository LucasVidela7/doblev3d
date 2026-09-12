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

    def __str__(self):
        return f"{self.nombre} - {self.fecha_desde}"