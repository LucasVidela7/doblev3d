from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("costos", "0002_remove_configuracioncostos_amortizacion_por_hora_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncostos",
            name="coste_plastico_kg_cantidad",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text=(
                    "Se usa desde 5 unidades en la calculadora y para kits. "
                    "Si queda en 0, se usa el coste estándar."
                ),
                max_digits=12,
                verbose_name="Coste plástico por kg para cantidad",
            ),
        ),
    ]