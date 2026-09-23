from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0023_configuracion_alias_pago"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="redondeo_precio_producto",
            field=models.PositiveIntegerField(
                default=100,
                help_text=(
                    "Los precios de lista de productos se redondean siempre hacia arriba "
                    "al próximo múltiplo configurado. Ejemplo: 100."
                ),
                verbose_name="Múltiplo de redondeo para precios",
            ),
        ),
    ]
