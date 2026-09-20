from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0011_configuracioncatalogo_estado_catalogo_y_avisos"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_generico",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 ¿Cómo estás? Te escribo de Doble V 3D."
                ),
                help_text="Podés usar {nombre}.",
                verbose_name="Mensaje general a clientes",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_pedido_listo",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 Tu pedido {codigo} de Doble V 3D ya está listo "
                    "para entregar. Cuando quieras coordinamos la entrega. ¡Gracias!"
                ),
                help_text=(
                    "Podés usar {nombre}, {codigo}, {total} y {fecha_entrega}."
                ),
                verbose_name="Mensaje de pedido listo",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_saldo",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 Te escribo por el pedido {codigo}. "
                    "Quedó un saldo pendiente de $ {saldo}. "
                    "Cuando puedas coordinamos el pago. ¡Gracias!"
                ),
                help_text=(
                    "Podés usar {nombre}, {codigo}, {saldo}, {total} y {pagado}."
                ),
                verbose_name="Mensaje de saldo pendiente",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_presupuesto",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 ¿Cómo estás? Te escribo por el presupuesto "
                    "{codigo} de Doble V 3D. Si querés hacer algún cambio o avanzar "
                    "con el pedido, avisame y lo revisamos."
                ),
                help_text=(
                    "Podés usar {nombre}, {codigo}, {total} y {fecha}."
                ),
                verbose_name="Mensaje de presupuesto pendiente",
            ),
        ),
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_reactivacion",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 ¿Cómo estás? Hace un tiempo que no hablamos y "
                    "quería consultarte si necesitabas volver a pedir alguno de "
                    "nuestros productos de Doble V 3D."
                ),
                help_text=(
                    "Podés usar {nombre}, {dias_sin_actividad} y {ultima_actividad}."
                ),
                verbose_name="Mensaje de reactivación",
            ),
        ),
    ]
