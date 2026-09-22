from django.db import migrations, models


RESPUESTA_NUEVA = (
    "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
    "Podés revisar el detalle completo acá:\n{url}\n\n"
    "Total de productos: {total}\n\n"
    "Para confirmar tu pedido solicitamos una seña del 30%: {senia}.\n\n"
    "El plazo estimado de entrega es de 3 a 10 días hábiles "
    "a partir del {fecha_hoy}.\n\n"
    "Si querés avanzar, realizá la seña y enviame el comprobante "
    "por acá. Una vez acreditada, tu pedido queda confirmado. 😊"
)

POST_NUEVO = (
    "Hola! 👋 Acabo de enviar la solicitud {codigo} desde el catálogo de "
    "Doble V 3D.\n\nDetalle de la solicitud:\n{url}\n\n"
    "Total de productos: {total}\n\n"
    "Quisiera coordinar disponibilidad y entrega."
)


def migrar_mensajes(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model("productos", "ConfiguracionCatalogo")
    for config in ConfiguracionCatalogo.objects.all():
        respuesta = (config.whatsapp_mensaje_respuesta_solicitud or "").strip()
        post = (config.whatsapp_mensaje_post_solicitud or "").strip()

        if "{detalle}" in respuesta and "{url}" not in respuesta:
            respuesta = respuesta.replace("{detalle}", "{url}")
            config.whatsapp_mensaje_respuesta_solicitud = respuesta

        if "{detalle}" in post and "{url}" not in post:
            post = post.replace("{detalle}", "{url}")
            config.whatsapp_mensaje_post_solicitud = post

        config.save(
            update_fields=[
                "whatsapp_mensaje_respuesta_solicitud",
                "whatsapp_mensaje_post_solicitud",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0016_asegurar_senia_fecha_respuesta"),
    ]

    operations = [
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_respuesta_solicitud",
            field=models.TextField(
                blank=True,
                default=RESPUESTA_NUEVA,
                help_text=(
                    "Podés usar {nombre}, {codigo}, {detalle}, {url}, {total}, "
                    "{senia}, {fecha_hoy} y {observaciones}."
                ),
                verbose_name="Mensaje para responder solicitudes",
            ),
        ),
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_post_solicitud",
            field=models.TextField(
                blank=True,
                default=POST_NUEVO,
                help_text=(
                    "Se abre hacia tu WhatsApp. Podés usar {nombre}, {codigo}, "
                    "{detalle}, {url}, {total} y {observaciones}."
                ),
                verbose_name="Mensaje del cliente después de solicitar",
            ),
        ),
        migrations.RunPython(migrar_mensajes, migrations.RunPython.noop),
    ]
