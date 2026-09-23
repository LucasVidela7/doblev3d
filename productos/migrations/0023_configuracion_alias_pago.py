from django.db import migrations, models


OLD_RESPUESTA = (
    "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
    "Podés revisar el detalle completo acá:\n{url}\n\n"
    "Total de productos: {total}\n\n"
    "Para confirmar tu pedido solicitamos una seña del 30%: {senia}.\n\n"
    "El plazo estimado de entrega es de 3 a 10 días hábiles "
    "a partir del {fecha_hoy}.\n\n"
    "Si querés avanzar, realizá la seña y enviame el comprobante "
    "por acá. Una vez acreditada, tu pedido queda confirmado. 😊"
)
NEW_RESPUESTA = (
    "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
    "Podés revisar el detalle completo acá:\n{url}\n\n"
    "Total de productos: {total}\n\n"
    "Para confirmar tu pedido solicitamos una seña del 30%: {senia}.\n\n"
    "{datos_pago}\n\n"
    "El plazo estimado de entrega es de 3 a 10 días hábiles "
    "a partir del {fecha_hoy}.\n\n"
    "Si querés avanzar, realizá la seña y enviame el comprobante "
    "por acá. Una vez acreditada, tu pedido queda confirmado. 😊"
)

OLD_LISTO_SALDO = (
    "Hola {nombre} 👋 Tu pedido de Doble V 3D ya está listo.\n\n"
    "{pedido}\n\n"
    "{cierre}"
)
NEW_LISTO_SALDO = (
    "Hola {nombre} 👋 Tu pedido de Doble V 3D ya está listo.\n\n"
    "{pedido}\n\n"
    "{datos_pago}\n\n"
    "{cierre}"
)

OLD_SALDO = (
    "Hola {nombre} 👋 Te escribo por tu pedido de Doble V 3D.\n\n"
    "{pedido}\n\n"
    "{cierre}"
)
NEW_SALDO = (
    "Hola {nombre} 👋 Te escribo por tu pedido de Doble V 3D.\n\n"
    "{pedido}\n\n"
    "{datos_pago}\n\n"
    "{cierre}"
)

OLD_MULTIPLES = (
    "Hola {nombre} 👋 Te paso el estado de tus {cantidad_pedidos} "
    "pedidos de Doble V 3D:\n\n"
    "{pedidos}\n\n"
    "{saldo_resumen}\n\n"
    "{cierre}"
)
NEW_MULTIPLES = (
    "Hola {nombre} 👋 Te paso el estado de tus {cantidad_pedidos} "
    "pedidos de Doble V 3D:\n\n"
    "{pedidos}\n\n"
    "{saldo_resumen}\n\n"
    "{datos_pago}\n\n"
    "{cierre}"
)


def actualizar_plantillas_default(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model(
        "productos",
        "ConfiguracionCatalogo",
    )
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_respuesta_solicitud=OLD_RESPUESTA,
    ).update(
        whatsapp_mensaje_respuesta_solicitud=NEW_RESPUESTA,
    )
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_cliente_pedido_listo_saldo=OLD_LISTO_SALDO,
    ).update(
        whatsapp_mensaje_cliente_pedido_listo_saldo=NEW_LISTO_SALDO,
    )
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_cliente_saldo=OLD_SALDO,
    ).update(
        whatsapp_mensaje_cliente_saldo=NEW_SALDO,
    )
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_cliente_multiples_pedidos=OLD_MULTIPLES,
    ).update(
        whatsapp_mensaje_cliente_multiples_pedidos=NEW_MULTIPLES,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0022_whatsapp_seguimiento_pagos"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_pago_alias",
            field=models.CharField(
                blank=True,
                default="doblev3d.mp",
                help_text=(
                    "Alias que se informa automáticamente cuando hay un pago pendiente."
                ),
                max_length=120,
                verbose_name="Alias de pago",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_pago_titular",
            field=models.CharField(
                blank=True,
                default="Lucas Andrés Videla",
                help_text="Nombre del titular que se muestra junto al alias.",
                max_length=180,
                verbose_name="Titular del medio de pago",
            ),
        ),
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_respuesta_solicitud",
            field=models.TextField(
                blank=True,
                default=NEW_RESPUESTA,
                help_text=(
                    "Podés usar {nombre}, {codigo}, {detalle}, {url}, {total}, "
                    "{senia}, {datos_pago}, {fecha_hoy} y {observaciones}."
                ),
                verbose_name="Mensaje para responder solicitudes",
            ),
        ),
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_pedido_listo_saldo",
            field=models.TextField(
                blank=True,
                default=NEW_LISTO_SALDO,
                help_text=(
                    "Se usa automáticamente cuando un pedido LISTO todavía tiene saldo. "
                    "Podés usar {nombre}, {pedido}, {codigo}, {url}, {total}, {pagado}, "
                    "{saldo}, {cantidad_pagos}, {datos_pago}, {fecha_entrega} y {cierre}."
                ),
                verbose_name="Mensaje de pedido listo con saldo",
            ),
        ),
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_saldo",
            field=models.TextField(
                blank=True,
                default=NEW_SALDO,
                help_text=(
                    "Podés usar {nombre}, {pedido}, {codigo}, {url}, {saldo}, {total}, "
                    "{pagado}, {cantidad_pagos}, {datos_pago} y {cierre}. Se usa para "
                    "pedidos en preparación o entregados que todavía tienen saldo."
                ),
                verbose_name="Mensaje de saldo pendiente",
            ),
        ),
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_multiples_pedidos",
            field=models.TextField(
                blank=True,
                default=NEW_MULTIPLES,
                help_text=(
                    "Podés usar {nombre}, {cantidad_pedidos}, {pedidos}, {saldo_total}, "
                    "{saldo_resumen}, {datos_pago}, {cantidad_listos}, "
                    "{cantidad_con_saldo} y {cierre}. {pedidos} incluye estado, "
                    "cantidad de pagos, total pagado, saldo y URL individual de cada pedido."
                ),
                verbose_name="Mensaje de múltiples pedidos",
            ),
        ),
        migrations.RunPython(
            actualizar_plantillas_default,
            migrations.RunPython.noop,
        ),
    ]
