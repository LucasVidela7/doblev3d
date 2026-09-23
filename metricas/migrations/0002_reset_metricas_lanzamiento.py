import os

from django.db import migrations


def reset_metricas_produccion(apps, schema_editor):
    entorno = (
        os.getenv("APP_ENV", "").strip().lower()
        or os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
    )
    if entorno != "production":
        print(f"METRICAS_RESET omitido entorno={entorno or 'desconocido'}")
        return

    EventoCatalogo = apps.get_model("metricas", "EventoCatalogo")
    antes = EventoCatalogo.objects.count()
    EventoCatalogo.objects.all().delete()
    despues = EventoCatalogo.objects.count()
    print(f"METRICAS_RESET antes={antes} despues={despues}")


class Migration(migrations.Migration):

    dependencies = [
        ("metricas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            reset_metricas_produccion,
            migrations.RunPython.noop,
        ),
    ]
