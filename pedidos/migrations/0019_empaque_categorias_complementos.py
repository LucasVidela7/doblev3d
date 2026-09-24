from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0018_empaques_etapa3"),
        ("productos", "0027_provision_empaque_comercial"),
    ]

    operations = [
        migrations.AddField(
            model_name="reglaempaque",
            name="tipo_producto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reglas_empaque",
                to="productos.tipoproducto",
                verbose_name="Categoría de producto",
            ),
        ),
        migrations.CreateModel(
            name="ReglaEmpaqueComplemento",
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
                        max_digits=12,
                    ),
                ),
                (
                    "insumo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reglas_empaque_complementarias",
                        to="productos.insumo",
                    ),
                ),
                (
                    "regla",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="complementos",
                        to="pedidos.reglaempaque",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="reglaempaquecomplemento",
            constraint=models.UniqueConstraint(
                fields=("regla", "insumo"),
                name="regla_empaque_complemento_unico",
            ),
        ),
        migrations.CreateModel(
            name="PedidoEmpaqueComplemento",
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
                        max_digits=12,
                    ),
                ),
                (
                    "costo_unitario_snapshot",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=12,
                    ),
                ),
                (
                    "costo_total_snapshot",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=12,
                    ),
                ),
                (
                    "insumo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="usos_empaque_complementarios",
                        to="productos.insumo",
                    ),
                ),
                (
                    "pedido_empaque",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="complementos",
                        to="pedidos.pedidoempaque",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AlterField(
            model_name="reglaempaque",
            name="alcance",
            field=models.CharField(
                choices=[
                    ("GENERAL", "General"),
                    ("CATEGORIA", "Categoría de producto"),
                    ("KIT", "Kit específico"),
                    ("PRODUCTO", "Producto específico"),
                ],
                default="GENERAL",
                max_length=20,
            ),
        ),
    ]
