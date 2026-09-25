# Generated manually for print-file library.

import django.db.models.deletion
from django.db import migrations, models

import productos.models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0030_seo_slugs_catalogo"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArchivoImpresion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "nombre",
                    models.CharField(max_length=180),
                ),
                (
                    "version",
                    models.CharField(blank=True, max_length=60),
                ),
                (
                    "archivo",
                    models.FileField(
                        max_length=320,
                        upload_to=productos.models.archivo_impresion_upload_to,
                    ),
                ),
                (
                    "nombre_original",
                    models.CharField(max_length=255),
                ),
                (
                    "tamano_bytes",
                    models.PositiveBigIntegerField(default=0),
                ),
                (
                    "sha256",
                    models.CharField(db_index=True, max_length=64),
                ),
                (
                    "placas",
                    models.JSONField(blank=True, default=list),
                ),
                (
                    "perfil_impresora",
                    models.CharField(blank=True, max_length=120),
                ),
                (
                    "notas",
                    models.TextField(blank=True),
                ),
                (
                    "activo",
                    models.BooleanField(default=True),
                ),
                (
                    "predeterminado",
                    models.BooleanField(default=False),
                ),
                (
                    "creado_en",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "actualizado_en",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="archivos_impresion",
                        to="productos.producto",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "-predeterminado",
                    "-actualizado_en",
                    "-id",
                ],
            },
        ),
    ]
