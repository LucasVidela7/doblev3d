from django.apps import AppConfig


class ProductosConfig(AppConfig):
    name = "productos"

    def ready(self):
        # ProductoImagen vive separado para mantener models.py enfocado en la
        # lógica productiva, pero debe importarse al cargar la app para que
        # Django registre el modelo y su relación inversa ``producto.imagenes``.
        from . import image_models  # noqa: F401
