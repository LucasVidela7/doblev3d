import uuid

from django.db import migrations, models


def completar_tokens(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    for pedido in Pedido.objects.filter(public_token__isnull=True).iterator():
        pedido.public_token = uuid.uuid4()
        pedido.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0016_solicitud_web_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="public_token",
            field=models.UUIDField(
                null=True,
                editable=False,
                db_index=True,
            ),
        ),
        migrations.RunPython(
            completar_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="pedido",
            name="public_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                db_index=True,
            ),
        ),
    ]
