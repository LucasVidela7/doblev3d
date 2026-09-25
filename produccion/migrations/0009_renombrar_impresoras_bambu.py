from django.db import migrations


def renombrar_impresoras(apps, schema_editor):
    Impresora = apps.get_model(
        "produccion",
        "Impresora",
    )

    Impresora.objects.filter(
        nombre="Bambu Lab A1 sin AMS",
    ).update(
        nombre="A1",
    )

    Impresora.objects.filter(
        nombre="Bambu Vieja",
    ).update(
        nombre="A1 COMBO",
    )


def revertir_nombres(apps, schema_editor):
    Impresora = apps.get_model(
        "produccion",
        "Impresora",
    )

    Impresora.objects.filter(
        nombre="A1",
    ).update(
        nombre="Bambu Lab A1 sin AMS",
    )

    Impresora.objects.filter(
        nombre="A1 COMBO",
    ).update(
        nombre="Bambu Vieja",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("produccion", "0008_comando_bambu_seguro"),
    ]

    operations = [
        migrations.RunPython(
            renombrar_impresoras,
            revertir_nombres,
        ),
    ]
