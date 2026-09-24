from io import BytesIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET
from PIL import Image, ImageDraw, ImageOps

from kits.imagenes import adjuntar_imagenes_reutilizadas
from kits.models import Kit

from .models import Producto


SOCIAL_IMAGE_SIZE = 1200
SOCIAL_CELL_SIZE = SOCIAL_IMAGE_SIZE // 2
SOCIAL_CACHE_SECONDS = 60 * 60 * 6


def _descargar_imagen(url):
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; DobleV3D-SocialPreview/1.0)"
            ),
            "Accept": "image/*",
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            data = response.read(8 * 1024 * 1024)
    except Exception:
        return None

    try:
        image = Image.open(BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image.load()
    except Exception:
        return None

    return image.convert("RGB")


def _foto_celda(image):
    return ImageOps.fit(
        image,
        (SOCIAL_CELL_SIZE, SOCIAL_CELL_SIZE),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def _collage_jpeg(urls):
    imagenes = []
    for url in urls[:4]:
        image = _descargar_imagen(url)
        if image is not None:
            imagenes.append(_foto_celda(image))

    if not imagenes:
        return None

    lienzo = Image.new(
        "RGB",
        (SOCIAL_IMAGE_SIZE, SOCIAL_IMAGE_SIZE),
        (245, 247, 251),
    )

    posiciones = (
        (0, 0),
        (SOCIAL_CELL_SIZE, 0),
        (0, SOCIAL_CELL_SIZE),
        (SOCIAL_CELL_SIZE, SOCIAL_CELL_SIZE),
    )

    # Si hay menos de cuatro fotos, repetimos el patrón disponible.
    # Evita cuadros vacíos en la vista previa y mantiene siempre el 2x2.
    for indice, posicion in enumerate(posiciones):
        image = imagenes[indice % len(imagenes)]
        lienzo.paste(image, posicion)

    # Separación mínima para que el 2x2 se entienda incluso con fotos similares.
    borde = 5
    dibujo = ImageDraw.Draw(lienzo)
    dibujo.rectangle(
        (
            SOCIAL_CELL_SIZE - borde,
            0,
            SOCIAL_CELL_SIZE + borde,
            SOCIAL_IMAGE_SIZE,
        ),
        fill=(255, 255, 255),
    )
    dibujo.rectangle(
        (
            0,
            SOCIAL_CELL_SIZE - borde,
            SOCIAL_IMAGE_SIZE,
            SOCIAL_CELL_SIZE + borde,
        ),
        fill=(255, 255, 255),
    )

    salida = BytesIO()
    lienzo.save(
        salida,
        format="JPEG",
        quality=88,
        optimize=True,
        progressive=True,
    )
    return salida.getvalue()


def _urls_sociales_kit(kit):
    if kit.modalidad == "FIJO":
        adjuntar_imagenes_reutilizadas([kit])
    else:
        productos = list(
            Producto.objects
            .filter(
                tipo_id=kit.tipo_producto_id,
                activo=True,
                solo_produccion=False,
            )
            .select_related("tipo")
            .order_by("nombre", "id")
        )
        kit.catalogo_productos_visuales = productos
        adjuntar_imagenes_reutilizadas(
            [kit],
            productos_por_tipo={
                kit.tipo_producto_id: productos,
            },
        )

    return [
        visual["imagen_url"]
        for visual in getattr(
            kit,
            "productos_visuales_collage",
            [],
        )
        if visual.get("imagen_url")
    ][:4]


@require_GET
def kit_social_preview(request, kit_id):
    kit = (
        Kit.objects
        .filter(
            id=kit_id,
            activo=True,
        )
        .select_related("tipo_producto")
        .prefetch_related(
            "componentes__producto__tipo",
        )
        .first()
    )
    if not kit:
        raise Http404("Kit no disponible")

    urls = _urls_sociales_kit(kit)
    if not urls:
        raise Http404("El kit no tiene imágenes disponibles")

    # La clave cambia cuando cambia cualquiera de las URLs del collage.
    cache_key = (
        "dv-social-kit-v1:"
        + str(kit.id)
        + ":"
        + "|".join(urls)
    )
    data = cache.get(cache_key)
    if data is None:
        data = _collage_jpeg(urls)
        if data is None:
            raise Http404("No se pudieron preparar las imágenes")
        cache.set(
            cache_key,
            data,
            SOCIAL_CACHE_SECONDS,
        )

    response = HttpResponse(
        data,
        content_type="image/jpeg",
    )
    response["Cache-Control"] = (
        f"public, max-age={SOCIAL_CACHE_SECONDS}"
    )
    response["Content-Disposition"] = (
        f'inline; filename="kit-{kit.id}-social.jpg"'
    )
    return response
