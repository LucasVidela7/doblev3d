import uuid

from django.db import migrations, models


def completar_tokens(apps, schema_editor):
    SolicitudWeb = apps.get_model("pedidos", "SolicitudWeb")
    for solicitud in SolicitudWeb.objects.filter(public_token__isnull=True):
        solicitud.public_token = uuid.uuid4()
        solicitud.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0014_snapshots_kits"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitudweb",
            name="public_token",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(completar_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="solicitudweb",
            name="public_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                db_index=True,
            ),
        ),
    ]
