from django.db import migrations, models


MENSAJE_ANTERIOR = (
    "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
    "Este es el detalle que recibimos:\n{detalle}\n\n"
    "Total de productos: {total}\n\n"
    "Te escribo para confirmar disponibilidad y coordinar la entrega."
)

MENSAJE_NUEVO = (
    "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
    "Este es el detalle que recibimos:\n{detalle}\n\n"
    "Total de productos: {total}\n\n"
    "Para confirmar tu pedido solicitamos una seña del 30%: {senia}.\n\n"
    "El plazo estimado de entrega es de 3 a 10 días hábiles "
    "a partir del {fecha_hoy}.\n\n"
    "Si querés avanzar, realizá la seña y enviame el comprobante "
    "por acá. Una vez acreditada, tu pedido queda confirmado. 😊"
)


def actualizar_mensaje_existente(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model("productos", "ConfiguracionCatalogo")
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_respuesta_solicitud=MENSAJE_ANTERIOR,
    ).update(
        whatsapp_mensaje_respuesta_solicitud=MENSAJE_NUEVO,
    )


def revertir_mensaje_existente(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model("productos", "ConfiguracionCatalogo")
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_respuesta_solicitud=MENSAJE_NUEVO,
    ).update(
        whatsapp_mensaje_respuesta_solicitud=MENSAJE_ANTERIOR,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0014_datos_legales_y_arrepentimiento"),
    ]

    operations = [
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_respuesta_solicitud",
            field=models.TextField(
                blank=True,
                default=MENSAJE_NUEVO,
                help_text=(
                    "Podés usar {nombre}, {codigo}, {detalle}, {total}, {senia}, "
                    "{fecha_hoy} y {observaciones}."
                ),
                verbose_name="Mensaje para responder solicitudes",
            ),
        ),
        migrations.RunPython(
            actualizar_mensaje_existente,
            revertir_mensaje_existente,
        ),
    ]
