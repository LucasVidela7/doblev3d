from django.db import migrations, models


def crear_configuracion_inicial(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model("productos", "ConfiguracionCatalogo")
    ConfiguracionCatalogo.objects.get_or_create(
        pk=1,
        defaults={
            "instagram_usuario": "doblev3d",
            "mostrar_instagram": True,
            "whatsapp_numero": "5491164760709",
            "mostrar_whatsapp": True,
            "whatsapp_mensaje": "Hola! Te escribo desde el catálogo de Doble V 3D.",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0008_productoimagen_ambiente"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfiguracionCatalogo",
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
                    "instagram_usuario",
                    models.CharField(
                        blank=True,
                        default="doblev3d",
                        help_text="Usuario sin @. Ejemplo: doblev3d",
                        max_length=100,
                        verbose_name="Instagram",
                    ),
                ),
                (
                    "mostrar_instagram",
                    models.BooleanField(
                        default=True,
                        verbose_name="Mostrar Instagram",
                    ),
                ),
                (
                    "whatsapp_numero",
                    models.CharField(
                        blank=True,
                        default="5491164760709",
                        help_text="Número con código de país. Ejemplo: 5491164760709",
                        max_length=30,
                        verbose_name="WhatsApp",
                    ),
                ),
                (
                    "mostrar_whatsapp",
                    models.BooleanField(
                        default=True,
                        verbose_name="Mostrar WhatsApp",
                    ),
                ),
                (
                    "whatsapp_mensaje",
                    models.CharField(
                        blank=True,
                        default="Hola! Te escribo desde el catálogo de Doble V 3D.",
                        max_length=240,
                        verbose_name="Mensaje inicial de WhatsApp",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configuración del catálogo",
                "verbose_name_plural": "Configuración del catálogo",
            },
        ),
        migrations.RunPython(
            crear_configuracion_inicial,
            migrations.RunPython.noop,
        ),
    ]
