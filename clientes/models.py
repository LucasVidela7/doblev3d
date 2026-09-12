from django.db import models


class Cliente(models.Model):

    nombre = models.CharField(
        max_length=150
    )

    telefono = models.CharField(
        max_length=30,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    observaciones = models.TextField(
        blank=True
    )

    activo = models.BooleanField(
        default=True
    )

    @property
    def codigo(self):
        return f"C{self.id:04d}" if self.id else "NUEVO"

    def __str__(self):
        return self.nombre