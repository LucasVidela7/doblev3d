import os
import re
from pathlib import Path
from uuid import uuid4

from imagekitio import ImageKit


MAX_IMAGE_BYTES = 15 * 1024 * 1024


class ImageKitNoConfigurado(RuntimeError):
    pass


class ImagenProductoInvalida(ValueError):
    pass


def imagekit_configurado():
    return bool(os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip())


def _cliente():
    private_key = os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip()
    if not private_key:
        raise ImageKitNoConfigurado(
            "Falta configurar IMAGEKIT_PRIVATE_KEY en el entorno."
        )
    return ImageKit(private_key=private_key)


def _nombre_seguro(nombre):
    nombre = Path(nombre or "imagen.jpg").name
    stem = re.sub(r"[^a-zA-Z0-9.-]+", "-", nombre).strip("-.")
    return stem or "imagen.jpg"


def validar_archivo(archivo):
    if archivo is None:
        raise ImagenProductoInvalida("Seleccioná una imagen.")

    content_type = (getattr(archivo, "content_type", "") or "").lower()
    if not content_type.startswith("image/"):
        raise ImagenProductoInvalida("El archivo seleccionado no es una imagen válida.")

    tamano = int(getattr(archivo, "size", 0) or 0)
    if tamano <= 0:
        raise ImagenProductoInvalida("La imagen está vacía.")
    if tamano > MAX_IMAGE_BYTES:
        raise ImagenProductoInvalida("La imagen supera el máximo permitido de 15 MB.")


def subir_imagen_producto(producto, archivo):
    validar_archivo(archivo)
    cliente = _cliente()

    nombre_original = _nombre_seguro(getattr(archivo, "name", "imagen.jpg"))
    nombre = f"{producto.codigo.lower()}-{uuid4().hex[:10]}-{nombre_original}"
    carpeta_base = os.getenv("IMAGEKIT_FOLDER", "/doblev3d/productos").strip()
    carpeta_base = "/" + carpeta_base.strip("/")
    carpeta = f"{carpeta_base}/{producto.id}"

    respuesta = cliente.files.upload(
        file=archivo.read(),
        file_name=nombre,
        folder=carpeta,
        tags=["doblev3d", "producto", producto.codigo.lower()],
        use_unique_file_name=True,
    )

    return {
        "file_id": respuesta.file_id,
        "url": respuesta.url,
        "thumbnail_url": getattr(respuesta, "thumbnail_url", "") or "",
        "nombre_archivo": getattr(respuesta, "name", "") or nombre,
        "ancho": getattr(respuesta, "width", None),
        "alto": getattr(respuesta, "height", None),
        "tamano_bytes": getattr(respuesta, "size", None),
    }


def eliminar_imagen_imagekit(file_id):
    if not file_id:
        return
    _cliente().files.delete(file_id)
