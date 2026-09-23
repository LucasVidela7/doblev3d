from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0018_configuracion_colores_y_producto_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="mostrar_productos_sin_foto",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Si se desactiva, los productos sin imágenes en el ambiente actual "
                    "se ocultan de los listados y de su detalle público. "
                    "Los kits y Gestión no se modifican."
                ),
                verbose_name="Mostrar productos sin foto",
            ),
        ),
    ]
