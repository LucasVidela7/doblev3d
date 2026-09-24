from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def inicializar_costo_promedio(apps, schema_editor):
    Insumo = apps.get_model("productos", "Insumo")
    for insumo in Insumo.objects.all().iterator():
        cantidad = Decimal(str(insumo.cantidad_compra or 0))
        precio = Decimal(str(insumo.precio_compra or 0))
        costo = (
            precio / cantidad
            if cantidad > 0
            else Decimal("0")
        )
        insumo.costo_promedio_unitario = costo
        insumo.save(update_fields=["costo_promedio_unitario"])


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0028_insumo_complementario_empaque"),
        ("pedidos", "0019_empaque_categorias_complementos"),
    ]

    operations = [
        migrations.AddField(
            model_name="insumo",
            name="costo_promedio_unitario",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text=(
                    "Costo promedio ponderado del stock actual. "
                    "Se actualiza automáticamente al registrar compras."
                ),
                max_digits=14,
                null=True,
            ),
        ),
        migrations.RunPython(
            inicializar_costo_promedio,
            migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name="CompraInsumo",
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
                ("fecha_compra", models.DateField()),
                (
                    "proveedor",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=160,
                    ),
                ),
                (
                    "observaciones",
                    models.TextField(
                        blank=True,
                        default="",
                    ),
                ),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                (
                    "gasto",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="compra_insumos",
                        to="pedidos.gasto",
                    ),
                ),
            ],
            options={"ordering": ["-fecha_compra", "-id"]},
        ),
        migrations.CreateModel(
            name="CompraInsumoItem",
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
                        max_digits=12,
                    ),
                ),
                (
                    "monto_total",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                    ),
                ),
                (
                    "costo_unitario_compra",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=14,
                    ),
                ),
                (
                    "stock_anterior",
                    models.DecimalField(
                        decimal_places=3,
                        default=0,
                        max_digits=12,
                    ),
                ),
                (
                    "costo_promedio_anterior",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                    ),
                ),
                (
                    "costo_promedio_nuevo",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                    ),
                ),
                (
                    "compra",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="productos.comprainsumo",
                    ),
                ),
                (
                    "insumo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="compras_items",
                        to="productos.insumo",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="comprainsumoitem",
            constraint=models.UniqueConstraint(
                fields=("compra", "insumo"),
                name="compra_insumo_item_unico",
            ),
        ),
    ]
