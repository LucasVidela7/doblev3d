from django.apps import AppConfig


class KitsConfig(AppConfig):
    name = "kits"

    def ready(self):
        from .ui_alignment import aplicar

        aplicar()
