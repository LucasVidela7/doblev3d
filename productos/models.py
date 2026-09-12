from decimal import Decimal, ROUND_CEILING

from django.db import models

from costos.models import ConfiguracionCostos


class TipoProducto(models.Model):
    nombre = models.CharField(
        max_length=100,
        unique=True
    )

    activo = models.BooleanField(
        default=True
    )

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    CATEGORIAS = [
        ("PRODUCTO", "Producto"),
        ("PERSONALIZADO", "Personalizado"),
        ("DESCARGADO", "Descargado"),
        ("OTRO", "Otro"),
    ]

    nombre = models.CharField(
        max_length=150
    )

    categoria = models.CharField(
        max_length=50,
        choices=CATEGORIAS
    )

    tipo = models.ForeignKey(
        TipoProducto,
        on_delete=models.PROTECT,
        related_name="productos"
    )

    horas = models.PositiveIntegerField(
        default=0
    )

    minutos = models.PositiveIntegerField(
        default=0
    )

    peso_gramos = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    margen_ganancia = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Ejemplo: 60 para 60%"
    )

    requiere_impresion = models.BooleanField(
        default=True
    )

    personalizable = models.BooleanField(
        default=False
    )

    stock = models.IntegerField(
        default=0
    )

    activo = models.BooleanField(
        default=True
    )

    def __str__(self):
        if self.id:
            return f"{self.codigo} - {self.nombre}"
        return self.nombre

    @property
    def horas_totales(self):
        return (
                Decimal(self.horas)
                +
                Decimal(self.minutos) / Decimal("60")
        )

    def obtener_configuracion(self):
        return (
            ConfiguracionCostos.objects
            .filter(activa=True)
            .order_by("-fecha_desde")
            .first()
        )

    @property
    def costo(self):

        if not self.requiere_impresion:
            return Decimal("0")

        config = self.obtener_configuracion()

        if not config:
            return Decimal("0")

        costo_luz = (
                self.horas_totales
                * config.coste_luz_hora
        )

        costo_material = (
                self.peso_gramos
                * config.coste_plastico_kg
                / Decimal("1000")
        )

        return (
                costo_luz
                +
                costo_material
        )

    @property
    def seguro(self):

        if not self.requiere_impresion:
            return Decimal("0")

        config = self.obtener_configuracion()

        if not config:
            return Decimal("0")

        amortizacion = (
                self.horas_totales
                * config.coste_amortizacion_hora
        )

        tasa_fallos = (
                config.tasa_fallos
                / Decimal("100")
        )

        return (
                (
                        amortizacion
                        +
                        self.costo
                )
                * tasa_fallos
                +
                amortizacion
        )

    @property
    def subtotal(self):

        if not self.requiere_impresion:
            return Decimal("0")

        margen = (
                self.margen_ganancia
                / Decimal("100")
        )

        if margen >= Decimal("1"):
            return Decimal("0")

        ganancia_teorica = (
                self.costo
                / (
                        Decimal("1")
                        -
                        margen
                )
                -
                self.costo
        )

        precio_sin_redondear = (
                self.costo
                +
                self.seguro
                +
                ganancia_teorica
        )

        multiplo = Decimal("500")

        return (
                (
                        precio_sin_redondear
                        / multiplo
                )
                .to_integral_value(
                    rounding=ROUND_CEILING
                )
                * multiplo
        )

    @property
    def ganancia(self):
        return (
                self.subtotal
                -
                self.costo
                -
                self.seguro
        )

    @property
    def codigo(self):
        return f"P{self.id:04d}" if self.id else "NUEVO"
