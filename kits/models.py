from django.db import models

from productos.models import Producto, TipoProducto


class Kit(models.Model):

    MODALIDADES = [
        (
            "LIBRE_CATEGORIA",
            "Libre por categoría",
        ),
        (
            "FIJO",
            "Composición fija",
        ),
    ]

    nombre = models.CharField(
        max_length=150,
        unique=True,
    )

    modalidad = models.CharField(
        max_length=30,
        choices=MODALIDADES,
        default="LIBRE_CATEGORIA",
    )

    # Para los kits LIBRE_CATEGORIA define qué productos
    # puede elegir el usuario.
    #
    # Para los kits FIJO puede quedar vacío porque la receta
    # se define en KitComponente.
    tipo_producto = models.ForeignKey(
        TipoProducto,
        on_delete=models.PROTECT,
        related_name="kits",
        null=True,
        blank=True,
    )

    # Se conserva por compatibilidad con los kits actuales.
    # En LIBRE_CATEGORIA indica cuántos productos elige el usuario.
    # En FIJO se sincroniza desde la suma de los componentes.
    cantidad_productos = models.PositiveIntegerField(
        default=1,
    )

    precio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    activo = models.BooleanField(
        default=True,
    )

    @property
    def codigo(self):
        return f"K{self.id:04d}" if self.id else "NUEVO"

    @property
    def cantidad_componentes_fijos(self):
        if not self.id:
            return 0

        return sum(
            componente.cantidad
            for componente in self.componentes.all()
        )

    def __str__(self):
        return self.nombre

    class Meta:
        ordering = ["nombre"]


class KitComponente(models.Model):

    kit = models.ForeignKey(
        Kit,
        on_delete=models.CASCADE,
        related_name="componentes",
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="kits_fijos",
    )

    cantidad = models.PositiveIntegerField(
        default=1,
    )

    def __str__(self):
        return (
            f"{self.kit.nombre} · "
            f"{self.producto.nombre} x{self.cantidad}"
        )

    class Meta:
        ordering = [
            "producto__nombre",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "kit",
                    "producto",
                ],
                name="kit_producto_fijo_unico",
            )
        ]
