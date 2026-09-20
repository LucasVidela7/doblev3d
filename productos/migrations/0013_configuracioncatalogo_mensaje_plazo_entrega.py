from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0012_configuracioncatalogo_mensajes_clientes"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="mensaje_plazo_entrega",
            field=models.CharField(
                blank=True,
                default=(
                    "Plazo de entrega: entre 3 y 10 días hábiles desde la confirmación "
                    "del presupuesto. El tiempo puede variar según stock, personalización "
                    "y disponibilidad de materiales."
                ),
                help_text=(
                    "Se muestra en la tienda, productos, kits y revisión de la solicitud."
                ),
                max_length=300,
                verbose_name="Plazo de entrega del catálogo",
            ),
        ),
    ]
