from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0027_provision_empaque_comercial"),
        ("kits", "0007_kit_max_repeticiones_producto"),
        ("pedidos", "0017_pedido_public_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReglaEmpaque",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=160)),
                (
                    "alcance",
                    models.CharField(
                        choices=[
                            ("GENERAL", "General"),
                            ("KIT", "Kit específico"),
                            ("PRODUCTO", "Producto específico"),
                        ],
                        default="GENERAL",
                        max_length=20,
                    ),
                ),
                ("desde_unidades", models.PositiveIntegerField(default=1)),
                ("hasta_unidades", models.PositiveIntegerField(blank=True, null=True)),
                ("cantidad_insumo", models.DecimalField(decimal_places=3, default=1, max_digits=12)),
                ("prioridad", models.PositiveIntegerField(default=100)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "insumo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reglas_empaque",
                        to="productos.insumo",
                    ),
                ),
                (
                    "kit",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reglas_empaque",
                        to="kits.kit",
                    ),
                ),
                (
                    "producto",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reglas_empaque",
                        to="productos.producto",
                    ),
                ),
            ],
            options={"ordering": ["prioridad", "desde_unidades", "id"]},
        ),
        migrations.CreateModel(
            name="PedidoEmpaque",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clave_paquete", models.CharField(max_length=100)),
                ("descripcion", models.CharField(max_length=200)),
                ("unidades_contenido", models.PositiveIntegerField(default=0)),
                ("cantidad", models.DecimalField(decimal_places=3, default=1, max_digits=12)),
                ("costo_unitario_snapshot", models.DecimalField(decimal_places=4, default=0, max_digits=12)),
                ("costo_total_snapshot", models.DecimalField(decimal_places=4, default=0, max_digits=12)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "insumo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="usos_empaque",
                        to="productos.insumo",
                    ),
                ),
                (
                    "pedido",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="empaques_usados",
                        to="pedidos.pedido",
                    ),
                ),
            ],
            options={"ordering": ["pedido_id", "clave_paquete"]},
        ),
        migrations.AddConstraint(
            model_name="pedidoempaque",
            constraint=models.UniqueConstraint(
                fields=("pedido", "clave_paquete"),
                name="pedido_empaque_paquete_unico",
            ),
        ),
    ]
