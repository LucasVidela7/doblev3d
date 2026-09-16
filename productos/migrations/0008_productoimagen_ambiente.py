from django.db import migrations, models

import productos.image_environment


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0007_productoimagen"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="productoimagen",
            name="producto_imagen_orden_unico",
        ),
        migrations.AddField(
            model_name="productoimagen",
            name="ambiente",
            field=models.CharField(
                db_index=True,
                default=productos.image_environment.entorno_imagenes,
                max_length=30,
            ),
        ),
        migrations.AddConstraint(
            model_name="productoimagen",
            constraint=models.UniqueConstraint(
                fields=("producto", "ambiente", "orden"),
                name="producto_imagen_ambiente_orden_unico",
            ),
        ),
    ]
