from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0017_solicitud_web_url_publica"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="colores_disponibles",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Un color por línea. Se ofrecen en productos y kits habilitados.",
                verbose_name="Colores disponibles",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="adicional_color_kit_base",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name="Cargo base por color en kit libre",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="adicional_color_kit_por_producto",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name="Cargo por producto por color en kit libre",
            ),
        ),
        migrations.AddField(
            model_name="producto",
            name="permite_elegir_color",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Permite elegir un color específico en la tienda. "
                    "No agrega costo en productos individuales."
                ),
            ),
        ),
    ]
