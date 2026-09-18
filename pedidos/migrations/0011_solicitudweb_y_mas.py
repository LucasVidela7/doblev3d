from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("kits", "0001_initial"),
        ("productos", "0001_initial"),
        ("pedidos", "0010_presupuesto_detallepresupuesto_y_mas"),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitudWeb",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("nombre", models.CharField(max_length=150)),
                ("telefono", models.CharField(max_length=40)),
                ("telefono_normalizado", models.CharField(blank=True, db_index=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("observaciones", models.TextField(blank=True)),
                ("estado", models.CharField(choices=[("NUEVA", "Nueva"), ("CONTACTADA", "Contactada"), ("CONVERTIDA", "Convertida"), ("RECHAZADA", "Rechazada")], db_index=True, default="NUEVA", max_length=20)),
                ("ip_hash", models.CharField(blank=True, db_index=True, max_length=64)),
                ("fingerprint", models.CharField(blank=True, db_index=True, max_length=64)),
                ("user_agent", models.CharField(blank=True, max_length=250)),
                ("presupuesto_generado", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="solicitud_web_origen", to="pedidos.presupuesto")),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.CreateModel(
            name="SolicitudWebItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_item", models.CharField(choices=[("PRODUCTO", "Producto"), ("KIT", "Kit")], max_length=20)),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("nombre_snapshot", models.CharField(max_length=200)),
                ("precio_base_unitario", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("adicional_unitario", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("precio_unitario", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("kit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_web", to="kits.kit")),
                ("producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_web", to="productos.producto")),
                ("solicitud", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="pedidos.solicitudweb")),
            ],
        ),
        migrations.CreateModel(
            name="SolicitudWebKitProducto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="productos_kit", to="pedidos.solicitudwebitem")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="productos.producto")),
            ],
        ),
    ]
