from decimal import Decimal

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0024_configuracion_redondeo_precio"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="incremento_insumos_por_defecto",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("10.00"),
                help_text=(
                    "Porcentaje de provisión aplicado al costo unitario de los insumos "
                    "que no tengan un porcentaje particular."
                ),
                max_digits=6,
                verbose_name="Incremento general de insumos",
            ),
        ),
        migrations.CreateModel(
            name="Insumo",
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
                ("nombre", models.CharField(max_length=160, unique=True)),
                (
                    "tipo_uso",
                    models.CharField(
                        choices=[
                            ("PRODUCTO", "Producto"),
                            ("EMPAQUE", "Empaque"),
                            ("DESPACHO", "Despacho"),
                        ],
                        default="PRODUCTO",
                        max_length=20,
                    ),
                ),
                (
                    "unidad_medida",
                    models.CharField(
                        choices=[
                            ("UNIDAD", "Unidad"),
                            ("METRO", "Metro"),
                            ("GRAMO", "Gramo"),
                            ("MILILITRO", "Mililitro"),
                        ],
                        default="UNIDAD",
                        max_length=20,
                    ),
                ),
                (
                    "precio_compra",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Precio total pagado por la compra o presentación.",
                        max_digits=12,
                    ),
                ),
                (
                    "cantidad_compra",
                    models.DecimalField(
                        decimal_places=3,
                        default=1,
                        help_text="Cantidad de unidades base incluidas en el precio de compra.",
                        max_digits=12,
                    ),
                ),
                (
                    "stock",
                    models.DecimalField(
                        decimal_places=3,
                        default=0,
                        help_text="Stock disponible expresado en la unidad base.",
                        max_digits=12,
                    ),
                ),
                ("proveedor", models.CharField(blank=True, default="", max_length=160)),
                ("url_referencia", models.URLField(blank=True, default="", max_length=500)),
                (
                    "incremento_personalizado",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text=(
                            "Si se deja vacío, utiliza el incremento general configurado "
                            "para todos los insumos."
                        ),
                        max_digits=6,
                        null=True,
                    ),
                ),
                ("precio_actualizado_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-activo", "tipo_uso", "nombre"],
            },
        ),
    ]
