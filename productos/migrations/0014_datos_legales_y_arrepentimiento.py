from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0013_configuracioncatalogo_mensaje_plazo_entrega"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="razon_social",
            field=models.CharField(
                blank=True,
                default="",
                max_length=180,
                verbose_name="Razón social / nombre del responsable",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="cuit",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
                verbose_name="CUIT",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="domicilio_legal",
            field=models.CharField(
                blank=True,
                default="",
                max_length=240,
                verbose_name="Domicilio comercial / legal",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="email_legal",
            field=models.EmailField(
                blank=True,
                default="",
                max_length=254,
                verbose_name="Email de contacto legal",
            ),
        ),
        migrations.CreateModel(
            name="SolicitudArrepentimiento",
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
                    "nombre",
                    models.CharField(
                        blank=True,
                        max_length=150,
                    ),
                ),
                (
                    "contacto",
                    models.CharField(
                        help_text="WhatsApp o email para responder la solicitud.",
                        max_length=180,
                    ),
                ),
                (
                    "referencia",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Pedido, presupuesto o comprobante si el cliente lo conoce."
                        ),
                        max_length=80,
                    ),
                ),
                (
                    "detalle",
                    models.TextField(blank=True),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("NUEVA", "Nueva"),
                            ("RESUELTA", "Resuelta"),
                        ],
                        default="NUEVA",
                        max_length=20,
                    ),
                ),
                (
                    "creada_en",
                    models.DateTimeField(auto_now_add=True),
                ),
            ],
            options={
                "ordering": ["-creada_en", "-id"],
            },
        ),
    ]
