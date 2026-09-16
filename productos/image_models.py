from django.core.exceptions import ValidationError
from django.db import models

from .image_environment import entorno_imagenes


class ProductoImagen(models.Model):
    """Referencia externa a una imagen de producto alojada en ImageKit.

    Cada producto puede tener como máximo dos imágenes por ambiente.
    ``orden=1`` es la imagen principal y ``orden=2`` la secundaria.
    """

    producto = models.ForeignKey(
        "productos.Producto",
        on_delete=models.CASCADE,
        related_name="imagenes",
    )
    ambiente = models.CharField(
        max_length=30,
        default=entorno_imagenes,
        db_index=True,
    )
    file_id = models.CharField(max_length=255, unique=True)
    url = models.URLField(max_length=1000)
    thumbnail_url = models.URLField(max_length=1000, blank=True)
    nombre_archivo = models.CharField(max_length=255, blank=True)
    orden = models.PositiveSmallIntegerField(default=1)
    ancho = models.PositiveIntegerField(null=True, blank=True)
    alto = models.PositiveIntegerField(null=True, blank=True)
    tamano_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "ambiente", "orden"],
                name="producto_imagen_ambiente_orden_unico",
            ),
        ]

    def clean(self):
        errores = {}
        if self.orden not in (1, 2):
            errores["orden"] = "La imagen debe ocupar la posición 1 o 2."

        if not self.ambiente:
            self.ambiente = entorno_imagenes()

        if self.producto_id:
            existentes = ProductoImagen.objects.filter(
                producto_id=self.producto_id,
                ambiente=self.ambiente,
            )
            if self.pk:
                existentes = existentes.exclude(pk=self.pk)
            if existentes.count() >= 2:
                errores["producto"] = (
                    "Cada producto puede tener como máximo 2 fotos por ambiente."
                )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if not self.ambiente:
            self.ambiente = entorno_imagenes()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def es_principal(self):
        return self.orden == 1

    def __str__(self):
        rol = "principal" if self.es_principal else "secundaria"
        return f"{self.producto} · {self.ambiente} · {rol}"
