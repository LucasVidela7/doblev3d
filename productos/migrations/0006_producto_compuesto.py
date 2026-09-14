from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0005_alter_producto_categoria"),
    ]

    operations = [
        migrations.AddField(
            model_name="producto",
            name="solo_produccion",
            field=models.BooleanField(
                default=False,
                help_text="Pieza interna de fabricación. No se ofrece como producto comercial.",
            ),
        ),
        migrations.AddField(
            model_name="producto",
            name="tipo_fabricacion",
            field=models.CharField(
                choices=[
                    ("SIMPLE", "Impresión simple"),
                    ("COMPUESTO", "Producto compuesto"),
                ],
                default="SIMPLE",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ProductoComponente",
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
                ("cantidad", models.PositiveIntegerField(default=1)),
                (
                    "componente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="usado_como_componente",
                        to="productos.producto",
                    ),
                ),
                (
                    "producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="componentes",
                        to="productos.producto",
                    ),
                ),
            ],
            options={"ordering": ["componente__nombre"]},
        ),
        migrations.AddConstraint(
            model_name="productocomponente",
            constraint=models.UniqueConstraint(
                fields=("producto", "componente"),
                name="producto_componente_unico",
            ),
        ),
    ]
