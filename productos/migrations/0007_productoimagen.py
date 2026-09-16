from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0006_producto_compuesto"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductoImagen",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("file_id", models.CharField(max_length=255, unique=True)),
                ("url", models.URLField(max_length=1000)),
                ("thumbnail_url", models.URLField(blank=True, max_length=1000)),
                ("nombre_archivo", models.CharField(blank=True, max_length=255)),
                ("orden", models.PositiveSmallIntegerField(default=1)),
                ("ancho", models.PositiveIntegerField(blank=True, null=True)),
                ("alto", models.PositiveIntegerField(blank=True, null=True)),
                ("tamano_bytes", models.PositiveBigIntegerField(blank=True, null=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                (
                    "producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="imagenes",
                        to="productos.producto",
                    ),
                ),
            ],
            options={"ordering": ["orden", "id"]},
        ),
        migrations.AddConstraint(
            model_name="productoimagen",
            constraint=models.UniqueConstraint(
                fields=("producto", "orden"),
                name="producto_imagen_orden_unico",
            ),
        ),
    ]
