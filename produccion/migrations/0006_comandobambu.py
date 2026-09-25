# Generated manually for Bambu command queue.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("produccion", "0005_control_alertas_ams"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComandoBambu",
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
                    "id_comando",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("STOP", "Detener impresión"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("EJECUTADO", "Ejecutado"),
                            ("ERROR", "Error"),
                        ],
                        default="PENDIENTE",
                        max_length=20,
                    ),
                ),
                (
                    "creado_en",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "resuelto_en",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True,
                    ),
                ),
                (
                    "impresora_estado",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comandos",
                        to="produccion.impresoraestadobambu",
                    ),
                ),
                (
                    "produccion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="comandos_bambu",
                        to="produccion.produccion",
                    ),
                ),
            ],
            options={
                "ordering": ["creado_en", "id"],
            },
        ),
    ]
