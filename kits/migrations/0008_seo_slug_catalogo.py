from django.db import migrations, models
from django.utils.text import slugify


def _slug_unico(modelo, nombre, pk, max_length=180):
    base = slugify(nombre)[: max_length - 20] or "kit"
    if base.isdigit():
        base = f"kit-{base}"
    candidato = base
    indice = 2
    while (
        modelo.objects
        .exclude(pk=pk)
        .filter(slug=candidato)
        .exists()
    ):
        sufijo = f"-{indice}"
        candidato = f"{base[:max_length-len(sufijo)]}{sufijo}"
        indice += 1
    return candidato


def completar_slugs(apps, schema_editor):
    Kit = apps.get_model("kits", "Kit")
    for kit in Kit.objects.all().order_by("id"):
        kit.slug = _slug_unico(
            Kit,
            kit.nombre,
            kit.pk,
        )
        kit.save(update_fields=["slug"])


def vaciar_slugs(apps, schema_editor):
    apps.get_model("kits", "Kit").objects.update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ("kits", "0007_kit_max_repeticiones_producto"),
    ]

    operations = [
        migrations.AddField(
            model_name="kit",
            name="slug",
            field=models.SlugField(
                max_length=180,
                unique=True,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="kit",
            name="descripcion_catalogo",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="kit",
            name="seo_titulo",
            field=models.CharField(max_length=180, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="kit",
            name="seo_descripcion",
            field=models.CharField(max_length=320, blank=True, default=""),
        ),
        migrations.RunPython(completar_slugs, vaciar_slugs),
        migrations.AlterField(
            model_name="kit",
            name="slug",
            field=models.SlugField(
                max_length=180,
                unique=True,
                blank=True,
            ),
        ),
    ]
}
