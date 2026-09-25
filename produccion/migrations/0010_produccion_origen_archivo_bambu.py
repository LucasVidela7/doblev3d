# Generated manually for Bambu Studio external-print association.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0032_archivoimpresion_cantidad_reemplazo"),
        ("produccion", "0009_renombrar_impresoras_bambu"),
    ]

    operations = [
        migrations.AddField(
            model_name="produccion",
            name="archivo_impresion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="producciones",
                to="productos.archivoimpresion",
            ),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_trabajo",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="produccion",
            name="origen",
            field=models.CharField(
                choices=[
                    ("GESTION", "Gestión"),
                    ("BAMBU_STUDIO", "Bambu Studio"),
                    ("MANUAL", "Manual"),
                ],
                default="GESTION",
                max_length=20,
            ),
        ),
    ]
