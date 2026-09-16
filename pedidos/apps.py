from django.apps import AppConfig


class PedidosConfig(AppConfig):
    name = "pedidos"

    def ready(self):
        # Importar señales al iniciar Django.
        from . import signals  # noqa: F401
