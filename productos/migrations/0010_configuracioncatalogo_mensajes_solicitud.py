from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0009_configuracioncatalogo"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_respuesta_solicitud",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
                    "Este es el detalle que recibimos:\n{detalle}\n\n"
                    "Total de productos: {total}\n\n"
                    "Te escribo para confirmar disponibilidad y coordinar la entrega."
                ),
                help_text=(
                    "Podés usar {nombre}, {codigo}, {detalle}, {total} y "
                    "{observaciones}."
                ),
                verbose_name="Mensaje para responder solicitudes",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_post_solicitud",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola! 👋 Acabo de enviar la solicitud {codigo} desde el catálogo "
                    "de Doble V 3D.\n\nDetalle:\n{detalle}\n\n"
                    "Total de productos: {total}\n\n"
                    "Quisiera coordinar disponibilidad y entrega."
                ),
                help_text=(
                    "Se abre hacia tu WhatsApp. Podés usar {nombre}, {codigo}, "
                    "{detalle}, {total} y {observaciones}."
                ),
                verbose_name="Mensaje del cliente después de solicitar",
            ),
        ),
    ]
