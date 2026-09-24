from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0025_insumos_base"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductoInsumo",
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
                (
                    "cantidad",
                    models.DecimalField(
                        decimal_places=3,
                        default=1,
                        help_text=(
                            "Cantidad de unidad base consumida por cada unidad "
                            "del producto."
                        ),
                        max_digits=12,
                    ),
                ),
                (
                    "insumo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="productos_asignados",
                        to="productos.insumo",
                    ),
                ),
                (
                    "producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insumos_asignados",
                        to="productos.producto",
                    ),
                ),
            ],
            options={
                "ordering": ["insumo__nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="productoinsumo",
            constraint=models.UniqueConstraint(
                fields=("producto", "insumo"),
                name="producto_insumo_unico",
            ),
        ),
    ]
