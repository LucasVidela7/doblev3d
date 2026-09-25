from django.db import migrations


def backfill_gcode_pendientes(apps, schema_editor):
    Produccion = apps.get_model(
        "produccion",
        "Produccion",
    )
    ArchivoImpresion = apps.get_model(
        "productos",
        "ArchivoImpresion",
    )

    principales = (
        ArchivoImpresion.objects
        .filter(
            activo=True,
            predeterminado=True,
        )
        .order_by(
            "producto_id",
            "cantidad_unidades",
            "-actualizado_en",
            "-id",
        )
    )

    for archivo in principales.iterator():
        Produccion.objects.filter(
            producto_id=archivo.producto_id,
            cantidad=archivo.cantidad_unidades,
            estado="PENDIENTE",
        ).update(
            archivo_impresion_id=archivo.id
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "productos",
            "0032_archivoimpresion_cantidad_reemplazo",
        ),
        (
            "produccion",
            "0010_produccion_origen_archivo_bambu",
        ),
    ]

    operations = [
        migrations.RunPython(
            backfill_gcode_pendientes,
            migrations.RunPython.noop,
        ),
    ]
