import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from productos.models import ArchivoImpresion


class Command(BaseCommand):
    help = "Verifica SHA-256 y tamaño de los G-code guardados."

    def handle(self, *args, **options):
        total = 0
        ok = 0
        missing = 0
        mismatches = 0

        for registro in (
            ArchivoImpresion.objects
            .filter(activo=True)
            .order_by("id")
            .iterator()
        ):
            total += 1

            nombre = str(
                registro.archivo.name
                or ""
            ).strip()

            if not nombre:
                missing += 1
                self.stdout.write(
                    f"PRINT FILE MISSING | id={registro.id} | "
                    f"producto={registro.producto_id} | sin ruta"
                )
                continue

            try:
                path = Path(
                    registro.archivo.path
                )
            except Exception:
                path = (
                    Path(settings.PRINT_FILES_ROOT)
                    / nombre
                )

            if not path.exists():
                missing += 1
                self.stdout.write(
                    f"PRINT FILE MISSING | id={registro.id} | "
                    f"producto={registro.producto_id} | path={nombre}"
                )
                continue

            digest = hashlib.sha256()
            size = 0

            with open(path, "rb") as handle:
                for block in iter(
                    lambda: handle.read(
                        1024 * 1024
                    ),
                    b"",
                ):
                    digest.update(block)
                    size += len(block)

            actual_sha = digest.hexdigest()
            expected_sha = str(
                registro.sha256
                or ""
            ).strip().lower()
            expected_size = int(
                registro.tamano_bytes
                or 0
            )

            if (
                actual_sha == expected_sha
                and (
                    expected_size <= 0
                    or size == expected_size
                )
            ):
                ok += 1
                self.stdout.write(
                    f"PRINT FILE OK | id={registro.id} | "
                    f"size={size} | sha256={actual_sha}"
                )
                continue

            mismatches += 1
            self.stdout.write(
                f"PRINT FILE MISMATCH | id={registro.id} | "
                f"db_size={expected_size} | real_size={size} | "
                f"db_sha256={expected_sha} | real_sha256={actual_sha} | "
                f"path={nombre}"
            )

        self.stdout.write(
            f"Print integrity summary | total={total} | "
            f"ok={ok} | missing={missing} | mismatches={mismatches}"
        )
