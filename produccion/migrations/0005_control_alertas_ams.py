# Generated manually for quality-control, alerts and AMS integration.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("produccion", "0004_impresoraestadobambu"),
    ]

    operations = [
        migrations.AddField(
            model_name="impresoraestadobambu",
            name="ams",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="impresoraestadobambu",
            name="carrete_externo",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="produccion",
            name="control_calidad_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="produccion",
            name="evento_fin_bambu",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="produccion",
            name="fin_impresion_detectado",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="produccion",
            name="resultado_control",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="produccion",
            name="reimpresion_de",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reimpresiones",
                to="produccion.produccion",
            ),
        ),
        migrations.AlterField(
            model_name="produccion",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("IMPRIMIENDO", "Imprimiendo"),
                    ("CONTROL", "Pendiente de control"),
                    ("LISTO", "Listo"),
                    ("FALLIDA", "Fallida"),
                    ("CANCELADO", "Cancelado"),
                ],
                default="PENDIENTE",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ConfiguracionProduccion",
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
                    "avisos_impresion_activos",
                    models.BooleanField(default=True),
                ),
                (
                    "avisar_antes_finalizar",
                    models.BooleanField(default=True),
                ),
                (
                    "minutos_aviso_finalizacion",
                    models.PositiveSmallIntegerField(default=15),
                ),
                (
                    "avisar_finalizacion",
                    models.BooleanField(default=True),
                ),
                (
                    "avisar_cancelacion",
                    models.BooleanField(default=True),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EventoBambu",
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
                    "clave",
                    models.CharField(max_length=180, unique=True),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("PROXIMO_FIN", "Próxima a finalizar"),
                            ("FINALIZADA", "Finalizada"),
                            ("CANCELADA", "Cancelada"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "creado_en",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "payload",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "impresora_estado",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eventos",
                        to="produccion.impresoraestadobambu",
                    ),
                ),
                (
                    "produccion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="eventos_bambu",
                        to="produccion.produccion",
                    ),
                ),
            ],
            options={
                "ordering": ["-creado_en", "-id"],
            },
        ),
    ]
