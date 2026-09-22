from django.db import migrations


BLOQUE_SENIA = (
    "Para confirmar tu pedido solicitamos una seña del 30%: {senia}."
)
BLOQUE_ENTREGA = (
    "El plazo estimado de entrega es de 3 a 10 días hábiles "
    "a partir del {fecha_hoy}."
)
BLOQUE_CIERRE = (
    "Si querés avanzar, realizá la seña y enviame el comprobante por acá. "
    "Una vez acreditada, tu pedido queda confirmado. 😊"
)


def asegurar_senia_y_fecha(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model("productos", "ConfiguracionCatalogo")

    for config in ConfiguracionCatalogo.objects.all():
        mensaje = (config.whatsapp_mensaje_respuesta_solicitud or "").strip()
        partes = [mensaje] if mensaje else []

        if "{senia}" not in mensaje:
            partes.append(BLOQUE_SENIA)
        if "{fecha_hoy}" not in mensaje:
            partes.append(BLOQUE_ENTREGA)
        if "{senia}" not in mensaje or "{fecha_hoy}" not in mensaje:
            partes.append(BLOQUE_CIERRE)

        nuevo_mensaje = "\n\n".join(parte for parte in partes if parte).strip()
        if nuevo_mensaje != mensaje:
            config.whatsapp_mensaje_respuesta_solicitud = nuevo_mensaje
            config.save(update_fields=["whatsapp_mensaje_respuesta_solicitud"])


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0015_configuracioncatalogo_senia_fecha_solicitud"),
    ]

    operations = [
        migrations.RunPython(
            asegurar_senia_y_fecha,
            migrations.RunPython.noop,
        ),
    ]
