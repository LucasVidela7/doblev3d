from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0009_detallepedido_precio_kit_manual"),
    ]

    operations = [
        migrations.CreateModel(
            name="Presupuesto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("APROBADO", "Aprobado"), ("RECHAZADO", "Rechazado")], default="PENDIENTE", max_length=20)),
                ("fecha_entrega", models.DateField(blank=True, null=True)),
                ("observaciones", models.TextField(blank=True)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="presupuestos", to="clientes.cliente")),
                ("pedido_generado", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="presupuesto_origen", to="pedidos.pedido")),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.CreateModel(
            name="DetallePresupuesto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_item", models.CharField(choices=[("PRODUCTO", "Producto"), ("KIT", "Kit"), ("PERSONALIZADO", "Personalizado")], max_length=20)),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("precio_lista_unitario", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("precio_unitario", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("precio_kit_manual", models.BooleanField(default=False)),
                ("costo_unitario", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("personalizado", models.BooleanField(default=False)),
                ("detalle_personalizacion", models.TextField(blank=True)),
                ("color_personalizacion", models.CharField(blank=True, max_length=100)),
                ("precio_total_personalizado", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("kit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="detalles_presupuesto", to="kits.kit")),
                ("presupuesto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="detalles", to="pedidos.presupuesto")),
                ("producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="detalles_presupuesto", to="productos.producto")),
            ],
        ),
        migrations.CreateModel(
            name="DetallePresupuestoKitProducto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("detalle", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="productos_kit", to="pedidos.detallepresupuesto")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="productos.producto")),
            ],
        ),
    ]
