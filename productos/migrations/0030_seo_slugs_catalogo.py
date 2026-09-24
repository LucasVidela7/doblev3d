from django.db import migrations, models
from django.utils.text import slugify


def _slug_unico(modelo, nombre, pk, prefijo, max_length):
    base = slugify(nombre)[: max_length - 20] or prefijo
    if base.isdigit():
        base = f"{prefijo}-{base}"
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
    TipoProducto = apps.get_model("productos", "TipoProducto")
    Producto = apps.get_model("productos", "Producto")

    for tipo in TipoProducto.objects.all().order_by("id"):
        tipo.slug = _slug_unico(
            TipoProducto,
            tipo.nombre,
            tipo.pk,
            "categoria",
            140,
        )
        tipo.save(update_fields=["slug"])

    for producto in Producto.objects.all().order_by("id"):
        producto.slug = _slug_unico(
            Producto,
            producto.nombre,
            producto.pk,
            "producto",
            180,
        )
        producto.save(update_fields=["slug"])


def vaciar_slugs(apps, schema_editor):
    apps.get_model("productos", "TipoProducto").objects.update(slug=None)
    apps.get_model("productos", "Producto").objects.update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0029_compras_insumos"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipoproducto",
            name="slug",
            field=models.SlugField(
                max_length=140,
                unique=True,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="tipoproducto",
            name="descripcion_catalogo",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tipoproducto",
            name="seo_titulo",
            field=models.CharField(max_length=160, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tipoproducto",
            name="seo_descripcion",
            field=models.CharField(max_length=320, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="producto",
            name="slug",
            field=models.SlugField(
                max_length=180,
                unique=True,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="producto",
            name="descripcion_catalogo",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="producto",
            name="seo_titulo",
            field=models.CharField(max_length=180, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="producto",
            name="seo_descripcion",
            field=models.CharField(max_length=320, blank=True, default=""),
        ),
        migrations.RunPython(completar_slugs, vaciar_slugs),
        migrations.AlterField(
            model_name="tipoproducto",
            name="slug",
            field=models.SlugField(
                max_length=140,
                unique=True,
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="producto",
            name="slug",
            field=models.SlugField(
                max_length=180,
                unique=True,
                blank=True,
            ),
        ),
    ]
}
