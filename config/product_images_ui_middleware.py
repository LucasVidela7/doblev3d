import html as html_lib
import re

from django.urls import reverse

from productos.image_environment import entorno_imagenes
from productos.image_models import ProductoImagen


STYLE = r"""
<style id="dv-product-images-style">
.dv-producto-fotos{
    margin-bottom:14px;
    padding:14px;
    border:1px solid #e4e7eb;
    border-radius:16px;
    background:#fff;
}
.dv-producto-fotos-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin-bottom:10px;
}
.dv-producto-fotos-title{font-size:10px;font-weight:900;color:#555d66}
.dv-producto-fotos-link{
    min-height:38px;
    padding:0 12px;
    border:1px solid #d9dee5;
    border-radius:11px;
    color:#24272b;
    background:#fff;
    text-decoration:none;
    font-size:9px;
    font-weight:900;
    display:inline-flex;
    align-items:center;
    justify-content:center;
}
.dv-producto-fotos-grid{display:grid;grid-template-columns:repeat(2,minmax(0,220px));gap:10px}
.dv-producto-foto{position:relative;aspect-ratio:4/3;border-radius:12px;overflow:hidden;background:#f0f2f4;border:1px solid #e5e7eb}
.dv-producto-foto img{width:100%;height:100%;object-fit:cover;display:block}
.dv-producto-foto span{position:absolute;left:8px;bottom:8px;padding:5px 7px;border-radius:999px;background:rgba(35,38,43,.84);color:#fff;font-size:7px;font-weight:900}
.dv-producto-foto-vacia{display:flex;align-items:center;justify-content:center;color:#969ba2;font-size:10px;font-weight:900}
@media(max-width:650px){.dv-producto-fotos-grid{grid-template-columns:1fr 1fr}.dv-producto-fotos-head{align-items:flex-start}.dv-producto-fotos-link{min-height:42px}}
</style>
"""


class ProductImagesUIMiddleware:
    """Muestra únicamente las fotos del producto del ambiente actual."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        if (
            not match
            or match.view_name != "productos:detalle"
            or response.status_code != 200
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        producto_id = match.kwargs.get("producto_id")
        if not producto_id:
            return response

        imagenes = list(
            ProductoImagen.objects
            .filter(
                producto_id=producto_id,
                ambiente=entorno_imagenes(),
            )
            .order_by("orden")[:2]
        )
        gestionar_url = reverse("productos:imagenes", args=[producto_id])

        try:
            contenido = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "dv-product-images-style" not in contenido and "</head>" in contenido:
            contenido = contenido.replace("</head>", STYLE + "\n</head>", 1)

        boton = (
            f'<a class="btn" href="{html_lib.escape(gestionar_url)}">'
            f'📷 FOTOS {len(imagenes)}/2</a>'
        )
        if "📷 FOTOS" not in contenido:
            contenido = re.sub(
                r'(<a class="btn dark" href="[^"]+">EDITAR PRODUCTO</a>)',
                r"\1" + boton,
                contenido,
                count=1,
            )

        fotos_html = []
        for imagen in imagenes:
            src = imagen.thumbnail_url or imagen.url
            rol = "PRINCIPAL" if imagen.orden == 1 else "SECUNDARIA"
            fotos_html.append(
                '<div class="dv-producto-foto">'
                f'<img src="{html_lib.escape(src)}" alt="Foto de producto">'
                f'<span>{rol}</span></div>'
            )
        while len(fotos_html) < 2:
            fotos_html.append(
                '<a class="dv-producto-foto dv-producto-foto-vacia" '
                f'href="{html_lib.escape(gestionar_url)}">+ AGREGAR FOTO</a>'
            )

        bloque = (
            '<div id="dv-producto-fotos-panel" class="dv-producto-fotos">'
            '<div class="dv-producto-fotos-head">'
            '<div class="dv-producto-fotos-title">FOTOS DEL PRODUCTO</div>'
            f'<a class="dv-producto-fotos-link" href="{html_lib.escape(gestionar_url)}">ADMINISTRAR FOTOS</a>'
            '</div><div class="dv-producto-fotos-grid">'
            + "".join(fotos_html)
            + "</div></div>"
        )

        if 'id="dv-producto-fotos-panel"' not in contenido:
            contenido = contenido.replace(
                '<div class="res">',
                bloque + '<div class="res">',
                1,
            )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
