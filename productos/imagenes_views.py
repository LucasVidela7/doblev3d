from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .image_environment import entorno_imagenes
from .image_models import ProductoImagen
from .imagekit_service import (
    ImagenProductoInvalida,
    ImageKitNoConfigurado,
    eliminar_imagen_imagekit,
    imagekit_configurado,
    subir_imagen_producto,
)
from .models import Producto


def _producto_con_imagenes(producto_id):
    return get_object_or_404(Producto, id=producto_id)


def _imagenes_del_entorno(producto, bloquear=False):
    queryset = ProductoImagen.objects.filter(
        producto=producto,
        ambiente=entorno_imagenes(),
    ).order_by("orden")
    if bloquear:
        queryset = queryset.select_for_update()
    return queryset


def imagenes_producto(request, producto_id):
    producto = _producto_con_imagenes(producto_id)
    imagenes = list(_imagenes_del_entorno(producto))
    return render(
        request,
        "productos/imagenes.html",
        {
            "producto": producto,
            "imagenes": imagenes,
            "cantidad_imagenes": len(imagenes),
            "imagekit_configurado": imagekit_configurado(),
            "ambiente_imagenes": entorno_imagenes(),
        },
    )


@transaction.atomic
def subir_imagen(request, producto_id):
    if request.method != "POST":
        return redirect("productos:imagenes", producto_id=producto_id)

    producto = get_object_or_404(Producto, id=producto_id)
    ambiente = entorno_imagenes()
    existentes = list(_imagenes_del_entorno(producto, bloquear=True))

    if len(existentes) >= 2:
        messages.error(request, "Este producto ya tiene el máximo de 2 fotos.")
        return redirect("productos:imagenes", producto_id=producto.id)

    archivo = request.FILES.get("imagen")
    datos = None
    try:
        datos = subir_imagen_producto(producto, archivo)
        orden_ocupado = {imagen.orden for imagen in existentes}
        orden = 1 if 1 not in orden_ocupado else 2
        ProductoImagen.objects.create(
            producto=producto,
            ambiente=ambiente,
            orden=orden,
            **datos,
        )
    except (ImagenProductoInvalida, ImageKitNoConfigurado) as error:
        messages.error(request, str(error))
        return redirect("productos:imagenes", producto_id=producto.id)
    except Exception:
        # Si ImageKit subió el archivo pero falló el guardado local, intentamos
        # limpiar el remoto recién creado. Ese archivo siempre pertenece al
        # ambiente actual porque la carpeta se define antes de la subida.
        if datos and datos.get("file_id"):
            try:
                eliminar_imagen_imagekit(datos["file_id"])
            except Exception:
                pass
        messages.error(
            request,
            "No se pudo subir la imagen a ImageKit. Revisá la configuración e intentá nuevamente.",
        )
        return redirect("productos:imagenes", producto_id=producto.id)

    messages.success(
        request,
        "Foto cargada correctamente."
        if orden == 2
        else "Foto principal cargada correctamente.",
    )
    return redirect("productos:imagenes", producto_id=producto.id)


@transaction.atomic
def eliminar_imagen(request, producto_id, imagen_id):
    if request.method != "POST":
        return redirect("productos:imagenes", producto_id=producto_id)

    producto = get_object_or_404(Producto, id=producto_id)
    ambiente = entorno_imagenes()
    imagen = get_object_or_404(
        ProductoImagen.objects.select_for_update(),
        id=imagen_id,
        producto=producto,
        ambiente=ambiente,
    )
    era_principal = imagen.orden == 1

    try:
        eliminar_imagen_imagekit(imagen.file_id)
    except ImageKitNoConfigurado as error:
        messages.error(request, str(error))
        return redirect("productos:imagenes", producto_id=producto.id)
    except Exception:
        messages.error(
            request,
            "No se pudo eliminar la foto de ImageKit. No se modificó el producto.",
        )
        return redirect("productos:imagenes", producto_id=producto.id)

    imagen.delete()

    if era_principal:
        secundaria = (
            ProductoImagen.objects
            .select_for_update()
            .filter(producto=producto, ambiente=ambiente, orden=2)
            .first()
        )
        if secundaria:
            secundaria.orden = 1
            secundaria.save(update_fields=["orden"])

    messages.success(request, "Foto eliminada correctamente.")
    return redirect("productos:imagenes", producto_id=producto.id)


@transaction.atomic
def hacer_principal(request, producto_id, imagen_id):
    if request.method != "POST":
        return redirect("productos:imagenes", producto_id=producto_id)

    producto = get_object_or_404(Producto, id=producto_id)
    ambiente = entorno_imagenes()
    imagen = get_object_or_404(
        ProductoImagen.objects.select_for_update(),
        id=imagen_id,
        producto=producto,
        ambiente=ambiente,
    )

    if imagen.orden == 1:
        return redirect("productos:imagenes", producto_id=producto.id)

    principal = (
        ProductoImagen.objects
        .select_for_update()
        .filter(producto=producto, ambiente=ambiente, orden=1)
        .first()
    )

    # Se usa una posición temporal únicamente dentro de la transacción para
    # evitar chocar con la restricción UNIQUE(producto, ambiente, orden).
    ProductoImagen.objects.filter(pk=imagen.pk).update(orden=99)
    if principal:
        ProductoImagen.objects.filter(pk=principal.pk).update(orden=2)
    ProductoImagen.objects.filter(pk=imagen.pk).update(orden=1)

    messages.success(request, "La foto seleccionada ahora es la principal.")
    return redirect("productos:imagenes", producto_id=producto.id)
