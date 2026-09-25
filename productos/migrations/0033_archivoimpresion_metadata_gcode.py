from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0032_archivoimpresion_cantidad_reemplazo"),
    ]

    operations = [
        migrations.AddField(
            model_name="archivoimpresion",
            name="peso_estimado_gramos",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="archivoimpresion",
            name="tiempo_estimado_minutos",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
            ),
        ),
    ]
