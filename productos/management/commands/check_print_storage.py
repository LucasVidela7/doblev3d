from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verifica lectura/escritura del almacenamiento privado de G-code."

    def handle(self, *args, **options):
        name = ".health/doblev3d-print-storage.txt"

        try:
            if default_storage.exists(name):
                default_storage.delete(name)

            saved = default_storage.save(
                name,
                ContentFile(b"doblev3d-storage-ok\n"),
            )

            if not default_storage.exists(saved):
                raise RuntimeError(
                    "El archivo de prueba no quedó disponible."
                )

            with default_storage.open(saved, "rb") as handle:
                contenido = handle.read()

            if contenido != b"doblev3d-storage-ok\n":
                raise RuntimeError(
                    "La lectura de prueba devolvió contenido inesperado."
                )

            default_storage.delete(saved)

        except Exception as error:
            raise CommandError(
                "No se pudo escribir/leer el almacenamiento "
                f"de G-code configurado en {settings.PRINT_FILES_ROOT}: "
                f"{error}"
            ) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Print storage OK"
            )
        )
