import gzip
import json
import os
import tempfile
import urllib.request

from django.conf import settings
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Vacía QA y carga una copia de los datos de producción."

    def handle(self, *args, **options):
        if not settings.IS_QA:
            raise RuntimeError("Este comando sólo puede ejecutarse en QA.")

        token = settings.DB_SYNC_TOKEN
        origen = settings.DB_SYNC_SOURCE_URL
        if not token or not origen:
            raise RuntimeError("Faltan DB_SYNC_TOKEN o DB_SYNC_SOURCE_URL.")

        self.stdout.write("Descargando fixture de producción...")
        solicitud = urllib.request.Request(
            origen,
            headers={
                "X-DB-Sync-Token": token,
                "User-Agent": "DobleV3D-QA-DB-Sync/1.0",
            },
        )
        with urllib.request.urlopen(solicitud, timeout=120) as respuesta:
            comprimido = respuesta.read()

        contenido = gzip.decompress(comprimido).decode("utf-8")
        fixture = json.loads(contenido)
        if not isinstance(fixture, list) or not fixture:
            raise RuntimeError("La exportación de producción llegó vacía o inválida.")

        self.stdout.write(
            f"Fixture validado: {len(fixture)} objetos. Vaciando QA..."
        )

        # Conserva el esquema y el historial de migraciones, pero elimina todos
        # los datos de las tablas administradas por Django antes de importar.
        call_command(
            "flush",
            interactive=False,
            verbosity=0,
            reset_sequences=True,
            allow_cascade=True,
            inhibit_post_migrate=True,
        )

        ruta = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                encoding="utf-8",
                delete=False,
            ) as temporal:
                temporal.write(contenido)
                ruta = temporal.name

            call_command("loaddata", ruta, verbosity=0)
        finally:
            if ruta and os.path.exists(ruta):
                os.unlink(ruta)

        # Las referencias de ImageKit son las mismas, pero QA filtra por el
        # campo ambiente. Adaptamos la copia para que las fotos sean visibles.
        from productos.image_models import ProductoImagen
        ProductoImagen.objects.filter(ambiente="production").update(ambiente="qa")

        self.stdout.write(
            self.style.SUCCESS(
                f"QA sincronizado con producción: {len(fixture)} objetos cargados."
            )
        )
