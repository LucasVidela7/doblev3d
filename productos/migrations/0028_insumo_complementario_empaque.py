from django.db import migrations, models


def marcar_complementarios_existentes(apps, schema_editor):
    Insumo = apps.get_model("productos", "Insumo")
    ReglaEmpaqueComplemento = apps.get_model(
        "pedidos",
        "ReglaEmpaqueComplemento",
    )
    ids = (
        ReglaEmpaqueComplemento.objects
        .values_list("insumo_id", flat=True)
        .distinct()
    )
    Insumo.objects.filter(id__in=ids).update(
        disponible_como_complementario=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0027_provision_empaque_comercial"),
        ("pedidos", "0019_empaque_categorias_complementos"),
    ]

    operations = [
        migrations.AddField(
            model_name="insumo",
            name="disponible_como_complementario",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Sólo aplica a insumos de tipo Empaque. Si está activo, "
                    "puede seleccionarse como sticker, tarjeta, cinta u otro "
                    "consumible complementario en las reglas de empaque."
                ),
                verbose_name="Disponible como complementario de empaque",
            ),
        ),
        migrations.RunPython(
            marcar_complementarios_existentes,
            migrations.RunPython.noop,
        ),
    ]
