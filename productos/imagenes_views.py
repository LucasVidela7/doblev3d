from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
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


def _quiere_json(request):
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


def _serializar_imagenes(producto):
    return [
        {
            "id": imagen.id,
            "url": imagen.url,
            "preview_url": imagen.thumbnail_url or imagen.url,
            "orden": imagen.orden,
            "principal": imagen.orden == 1,
            "nombre": imagen.nombre_archivo,
            "ancho": imagen.ancho,
            "alto": imagen.alto,
            "tamano_bytes": imagen.tamano_bytes,
        }
        for imagen in _imagenes_del_entorno(producto)
    ]


def _json_ok(producto, mensaje, status=200):
    return JsonResponse(
        {
            "ok": True,
            "message": mensaje,
            "imagenes": _serializar_imagenes(producto),
        },
        status=status,
    )


def _json_error(producto, mensaje, status=400):
    return JsonResponse(
        {
            "ok": False,
            "message": mensaje,
            "imagenes": _serializar_imagenes(producto),
        },
        status=status,
    )


def _eliminar_remoto_silencioso(file_id):
    if not file_id:
        return
    try:
        eliminar_imagen_imagekit(file_id)
    except Exception:
        # El reemplazo ya quedó confirmado localmente. Si ImageKit no permite
        # limpiar el archivo anterior, preferimos un huérfano remoto antes que
        # perder la nueva foto válida del producto.
        pass


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
    producto = get_object_or_404(Producto, id=producto_id)
    quiere_json = _quiere_json(request)

    if request.method != "POST":
        if quiere_json:
            return _json_error(producto, "Método no permitido.", status=405)
        return redirect("productos:imagenes", producto_id=producto_id)

    ambiente = entorno_imagenes()
    existentes = list(_imagenes_del_entorno(producto, bloquear=True))

    if len(existentes) >= 2:
        mensaje = "Este producto ya tiene el máximo de 2 fotos."
        if quiere_json:
            return _json_error(producto, mensaje, status=409)
        messages.error(request, mensaje)
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
        mensaje = str(error)
        if quiere_json:
            return _json_error(producto, mensaje, status=400)
        messages.error(request, mensaje)
        return redirect("productos:imagenes", producto_id=producto.id)
    except Exception:
        if datos and datos.get("file_id"):
            _eliminar_remoto_silencioso(datos["file_id"])
        mensaje = (
            "No se pudo subir la imagen a ImageKit. "
            "Revisá la configuración e intentá nuevamente."
        )
        if quiere_json:
            return _json_error(producto, mensaje, status=502)
        messages.error(request, mensaje)
        return redirect("productos:imagenes", producto_id=producto.id)

    mensaje = (
        "Foto cargada correctamente."
        if orden == 2
        else "Foto principal cargada correctamente."
    )
    if quiere_json:
        return _json_ok(producto, mensaje)
    messages.success(request, mensaje)
    return redirect("productos:imagenes", producto_id=producto.id)


@transaction.atomic
def reemplazar_imagen(request, producto_id, orden):
    """Reemplaza una posición conservando la foto anterior si la nueva falla."""
    producto = get_object_or_404(Producto, id=producto_id)
    quiere_json = _quiere_json(request)

    if request.method != "POST":
        if quiere_json:
            return _json_error(producto, "Método no permitido.", status=405)
        return redirect("productos:editar", producto_id=producto_id)

    if orden not in (1, 2):
        return _json_error(producto, "Posición de foto inválida.", status=400)

    ambiente = entorno_imagenes()
    actual = get_object_or_404(
        ProductoImagen.objects.select_for_update(),
        producto=producto,
        ambiente=ambiente,
        orden=orden,
    )
    archivo = request.FILES.get("imagen")
    datos = None

    try:
        # 1) Subimos primero la nueva. Hasta acá la foto actual sigue intacta.
        datos = subir_imagen_producto(producto, archivo)
        file_id_anterior = actual.file_id

        # 2) Reutilizamos el mismo registro y posición para no abrir una ventana
        #    sin principal/secundaria ni chocar con la restricción UNIQUE.
        actual.file_id = datos["file_id"]
        actual.url = datos["url"]
        actual.thumbnail_url = datos.get("thumbnail_url", "")
        actual.nombre_archivo = datos.get("nombre_archivo", "")
        actual.ancho = datos.get("ancho")
        actual.alto = datos.get("alto")
        actual.tamano_bytes = datos.get("tamano_bytes")
        actual.save(
            update_fields=[
                "file_id",
                "url",
                "thumbnail_url",
                "nombre_archivo",
                "ancho",
                "alto",
                "tamano_bytes",
            ]
        )

        # 3) Recién después del COMMIT intentamos limpiar el archivo anterior.
        transaction.on_commit(
            lambda old_id=file_id_anterior: _eliminar_remoto_silencioso(old_id),
            robust=True,
        )
    except (ImagenProductoInvalida, ImageKitNoConfigurado) as error:
        return _json_error(producto, str(error), status=400)
    except Exception:
        if datos and datos.get("file_id"):
            _eliminar_remoto_silencioso(datos["file_id"])
        return _json_error(
            producto,
            "No se pudo reemplazar la foto. La imagen anterior se conservó.",
            status=502,
        )

    rol = "principal" if orden == 1 else "secundaria"
    mensaje = f"Foto {rol} reemplazada correctamente."
    if quiere_json:
        return _json_ok(producto, mensaje)
    messages.success(request, mensaje)
    return redirect("productos:editar", producto_id=producto.id)


@transaction.atomic
def eliminar_imagen(request, producto_id, imagen_id):
    producto = get_object_or_404(Producto, id=producto_id)
    quiere_json = _quiere_json(request)

    if request.method != "POST":
        if quiere_json:
            return _json_error(producto, "Método no permitido.", status=405)
        return redirect("productos:imagenes", producto_id=producto_id)

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
        mensaje = str(error)
        if quiere_json:
            return _json_error(producto, mensaje, status=400)
        messages.error(request, mensaje)
        return redirect("productos:imagenes", producto_id=producto.id)
    except Exception:
        mensaje = "No se pudo eliminar la foto de ImageKit. No se modificó el producto."
        if quiere_json:
            return _json_error(producto, mensaje, status=502)
        messages.error(request, mensaje)
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

    mensaje = "Foto eliminada correctamente."
    if quiere_json:
        return _json_ok(producto, mensaje)
    messages.success(request, mensaje)
    return redirect("productos:imagenes", producto_id=producto.id)


@transaction.atomic
def hacer_principal(request, producto_id, imagen_id):
    producto = get_object_or_404(Producto, id=producto_id)
    quiere_json = _quiere_json(request)

    if request.method != "POST":
        if quiere_json:
            return _json_error(producto, "Método no permitido.", status=405)
        return redirect("productos:imagenes", producto_id=producto_id)

    ambiente = entorno_imagenes()
    imagen = get_object_or_404(
        ProductoImagen.objects.select_for_update(),
        id=imagen_id,
        producto=producto,
        ambiente=ambiente,
    )

    if imagen.orden == 1:
        if quiere_json:
            return _json_ok(producto, "Esta foto ya es la principal.")
        return redirect("productos:imagenes", producto_id=producto.id)

    principal = (
        ProductoImagen.objects
        .select_for_update()
        .filter(producto=producto, ambiente=ambiente, orden=1)
        .first()
    )

    ProductoImagen.objects.filter(pk=imagen.pk).update(orden=99)
    if principal:
        ProductoImagen.objects.filter(pk=principal.pk).update(orden=2)
    ProductoImagen.objects.filter(pk=imagen.pk).update(orden=1)

    mensaje = "La foto seleccionada ahora es la principal."
    if quiere_json:
        return _json_ok(producto, mensaje)
    messages.success(request, mensaje)
    return redirect("productos:imagenes", producto_id=producto.id)
