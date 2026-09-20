from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactoCliente",
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
                    "canal",
                    models.CharField(
                        default="WHATSAPP",
                        max_length=20,
                    ),
                ),
                (
                    "motivo",
                    models.CharField(
                        choices=[
                            ("GENERICO", "Contacto general"),
                            ("PEDIDO_LISTO", "Pedido listo"),
                            ("SALDO", "Saldo pendiente"),
                            ("PRESUPUESTO", "Presupuesto pendiente"),
                            ("REACTIVACION", "Reactivar cliente"),
                        ],
                        default="GENERICO",
                        max_length=30,
                    ),
                ),
                (
                    "referencia",
                    models.CharField(
                        blank=True,
                        max_length=40,
                    ),
                ),
                (
                    "mensaje",
                    models.TextField(blank=True),
                ),
                (
                    "iniciado_en",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "cliente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contactos",
                        to="clientes.cliente",
                    ),
                ),
            ],
            options={
                "ordering": ["-iniciado_en", "-id"],
            },
        ),
    ]
