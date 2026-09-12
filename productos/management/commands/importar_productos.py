import csv
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from productos.models import Producto, TipoProducto


class Command(BaseCommand):
    help = "Importa productos desde el CSV de Google Sheets"

    def add_arguments(self, parser):
        parser.add_argument(
            "archivo",
            type=str,
            help="Ruta del archivo CSV"
        )

    def limpiar_numero(self, valor):
        if not valor:
            return 0

        numeros = re.findall(r"[\d,.]+", str(valor))

        if not numeros:
            return 0

        valor = numeros[0]

        valor = valor.replace(".", "")
        valor = valor.replace(",", ".")

        return float(valor)

    def limpiar_entero(self, valor):
        if not valor:
            return 0

        numeros = re.findall(r"\d+", str(valor))

        if not numeros:
            return 0

        return int(numeros[0])

    def convertir_booleano(self, valor):
        return str(valor).strip().upper() in (
            "SI",
            "SÍ",
            "TRUE",
            "1",
        )

    @transaction.atomic
    def handle(self, *args, **options):

        archivo = options["archivo"]

        creados = 0
        actualizados = 0

        with open(
            archivo,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as csvfile:

            lector = csv.DictReader(csvfile)

            for fila in lector:

                nombre = fila.get(
                    "PRODUCTO",
                    ""
                ).strip()

                if not nombre:
                    continue

                nombre_tipo = fila.get(
                    "TIPO",
                    "OTRO"
                ).strip().upper()

                if not nombre_tipo:
                    nombre_tipo = "OTRO"

                tipo, _ = TipoProducto.objects.get_or_create(
                    nombre=nombre_tipo,
                    defaults={
                        "activo": True
                    }
                )

                producto, creado = Producto.objects.update_or_create(

                    nombre=nombre,

                    defaults={

                        # La categoría vieja
                        # KIT SENSORIAL ahora pasa
                        # a PRODUCTO.
                        "categoria": "PRODUCTO",

                        "tipo": tipo,

                        "horas": self.limpiar_entero(
                            fila.get("H")
                        ),

                        "minutos": self.limpiar_entero(
                            fila.get("M")
                        ),

                        "peso_gramos": self.limpiar_numero(
                            fila.get("P")
                        ),

                        "margen_ganancia": self.limpiar_numero(
                            fila.get("%")
                        ),

                        "requiere_impresion":
                            self.convertir_booleano(
                                fila.get(
                                    "REQUIERE IMPRESION"
                                )
                            ),

                        "personalizable":
                            self.convertir_booleano(
                                fila.get(
                                    "PERSONALIZABLE"
                                )
                            ),

                        "stock": self.limpiar_entero(
                            fila.get("STOCK")
                        ),

                        "activo":
                            self.convertir_booleano(
                                fila.get("ACTIVO")
                            ),
                    }
                )

                if creado:
                    creados += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"CREADO: "
                            f"{producto.codigo} - "
                            f"{producto.nombre}"
                        )
                    )

                else:
                    actualizados += 1

                    self.stdout.write(
                        self.style.WARNING(
                            f"ACTUALIZADO: "
                            f"{producto.codigo} - "
                            f"{producto.nombre}"
                        )
                    )

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"Importación terminada. "
                f"Creados: {creados} | "
                f"Actualizados: {actualizados}"
            )
        )