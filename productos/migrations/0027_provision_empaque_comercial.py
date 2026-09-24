from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0026_producto_insumos"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="provision_empaque_unitaria",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text=(
                    "Costo interno estimado de empaque considerado al calcular "
                    "precios comerciales. Nunca se muestra como adicional al cliente."
                ),
                max_digits=12,
                verbose_name="Provisión comercial de empaque por unidad",
            ),
        ),
    ]
