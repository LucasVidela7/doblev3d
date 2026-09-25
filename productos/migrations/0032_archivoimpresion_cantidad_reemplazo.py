# Generated manually for quantity-based print file mappings.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0031_archivoimpresion"),
    ]

    operations = [
        migrations.AddField(
            model_name="archivoimpresion",
            name="cantidad_unidades",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Cantidad de unidades del producto incluidas "
                    "en este archivo de impresión."
                ),
            ),
        ),
        migrations.AddField(
            model_name="archivoimpresion",
            name="reemplaza_a",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reemplazos",
                to="productos.archivoimpresion",
            ),
        ),
        migrations.AlterModelOptions(
            name="archivoimpresion",
            options={
                "ordering": [
                    "cantidad_unidades",
                    "-predeterminado",
                    "-actualizado_en",
                    "-id",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="archivoimpresion",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("predeterminado", True)
                ),
                fields=(
                    "producto",
                    "cantidad_unidades",
                ),
                name=(
                    "uniq_archivo_predeterminado_"
                    "producto_cantidad"
                ),
            ),
        ),
    ]
