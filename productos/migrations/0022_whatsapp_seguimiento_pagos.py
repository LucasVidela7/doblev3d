from django.db import migrations, models


OLD_LISTO = (
    "Hola {nombre} 👋 Tu pedido {codigo} de Doble V 3D ya está listo "
    "para entregar. Cuando quieras coordinamos la entrega. ¡Gracias!"
)
NEW_LISTO = (
    "Hola {nombre} 👋 Tu pedido de Doble V 3D ya está listo "
    "para entregar.\n\n"
    "{pedido}\n\n"
    "{cierre}"
)

OLD_SALDO = (
    "Hola {nombre} 👋 Te escribo por el pedido {codigo}. "
    "Quedó un saldo pendiente de $ {saldo}. "
    "Cuando puedas coordinamos el pago. ¡Gracias!"
)
NEW_SALDO = (
    "Hola {nombre} 👋 Te escribo por tu pedido de Doble V 3D.\n\n"
    "{pedido}\n\n"
    "{cierre}"
)

OLD_MULTIPLES = (
    "Hola {nombre} 👋 Te escribo por {cantidad_pedidos} pedidos "
    "que tenés activos en Doble V 3D:\n\n"
    "{pedidos}\n\n"
    "*Saldo total pendiente: ${saldo_total}*\n\n"
    "Cuando puedas, escribinos y coordinamos el pago 😊"
)
NEW_MULTIPLES = (
    "Hola {nombre} 👋 Te paso el estado de tus {cantidad_pedidos} "
    "pedidos de Doble V 3D:\n\n"
    "{pedidos}\n\n"
    "{saldo_resumen}\n\n"
    "{cierre}"
)


def actualizar_plantillas_default(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model(
        "productos",
        "ConfiguracionCatalogo",
    )
    ConfiguracionCatalogo.objects.filter(
        whatsapp_mensaje_cliente_pedido_listo=OLD_LISTO,
    ).update(
        whatsapp_mensaje_cliente_pedido_listo=NEW_LISTO,
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
        ("productos", "0021_configuracion_pedido_aprobado"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_pedido_listo_saldo",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 Tu pedido de Doble V 3D ya está listo.\n\n"
                    "{pedido}\n\n"
                    "{cierre}"
                ),
                help_text=(
                    "Se usa automáticamente cuando un pedido LISTO todavía tiene saldo. "
                    "Podés usar {nombre}, {pedido}, {codigo}, {url}, {total}, {pagado}, "
                    "{saldo}, {cantidad_pagos}, {fecha_entrega} y {cierre}."
                ),
                verbose_name="Mensaje de pedido listo con saldo",
            ),
        ),
        migrations.AlterField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_pedido_listo",
            field=models.TextField(
                blank=True,
                default=NEW_LISTO,
                help_text=(
                    "Podés usar {nombre}, {pedido}, {codigo}, {url}, {total}, "
                    "{pagado}, {saldo}, {cantidad_pagos}, {fecha_entrega} y {cierre}. "
                    "{pedido} incluye estado, pagos, saldo y URL pública."
                ),
                verbose_name="Mensaje de pedido listo y pagado",
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
                    "{pagado}, {cantidad_pagos} y {cierre}. Se usa para pedidos en "
                    "preparación o entregados que todavía tienen saldo."
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
                    "{saldo_resumen}, {cantidad_listos}, {cantidad_con_saldo} y {cierre}. "
                    "{pedidos} "
                    "incluye estado, cantidad de pagos, total pagado, saldo y URL "
                    "individual de cada pedido."
                ),
                verbose_name="Mensaje de múltiples pedidos",
            ),
        ),
        migrations.RunPython(
            actualizar_plantillas_default,
            migrations.RunPython.noop,
        ),
    ]
