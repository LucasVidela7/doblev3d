import html
import re

from django.templatetags.static import static
from django.urls import reverse

from productos.models import ConfiguracionCatalogo


HEADER_STYLE = r"""
<style id="dv-catalog-contact-style">
:root{--dv-catalog-header-height:68px}
body{padding-top:var(--dv-catalog-header-height)!important}
header.shell.topbar,
header.shell.top{display:none!important}
.toolbar{top:var(--dv-catalog-header-height)!important}
.dv-catalog-header{
    position:fixed;inset:0 0 auto 0;z-index:110;
    height:var(--dv-catalog-header-height);
    border-bottom:1px solid rgba(19,74,154,.12);
    background:rgba(255,255,255,.96);
    box-shadow:0 7px 22px rgba(18,31,52,.08);
    backdrop-filter:blur(14px);
    -webkit-backdrop-filter:blur(14px)
}
.dv-catalog-header__inner{
    width:min(1180px,calc(100% - 24px));height:100%;margin:0 auto;
    display:flex;align-items:center;justify-content:space-between;gap:14px
}
.dv-catalog-header__brand{
    min-width:0;display:inline-flex;align-items:center;gap:9px;
    color:#0d376f;text-decoration:none
}
.dv-catalog-header__brand img{width:48px;height:48px;object-fit:contain;flex:0 0 auto}
.dv-catalog-header__brand strong{
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
    font-size:.92rem;font-weight:950
}
.dv-catalog-header__actions{display:flex;align-items:center;gap:6px}
.dv-catalog-header__action{
    position:relative;width:42px;height:42px;flex:0 0 auto;
    display:inline-grid;place-items:center;padding:0;
    border:1px solid #dfe5ef;border-radius:13px;background:#fff;
    color:#134a9a;text-decoration:none;cursor:pointer;
    box-shadow:0 4px 12px rgba(19,74,154,.04);
    transition:transform .15s ease,box-shadow .15s ease;
    -webkit-tap-highlight-color:transparent
}
.dv-catalog-header__action svg{
    width:21px;height:21px;fill:none;stroke:currentColor;stroke-width:2;
    stroke-linecap:round;stroke-linejoin:round
}
.dv-catalog-header__help{font:inherit;background:#eef4ff;color:#134a9a;font-size:1rem;font-weight:950}
.dv-catalog-header__instagram{
    border-color:transparent;
    background:linear-gradient(145deg,#5b51d8 0%,#c13584 45%,#f77737 100%);
    color:#fff
}
.dv-catalog-header__whatsapp{border-color:#25d366;background:#25d366;color:#fff}
.dv-catalog-header__cart{border-color:#134a9a;background:#134a9a;color:#fff}
.dv-catalog-header__label{
    position:absolute!important;width:1px!important;height:1px!important;
    padding:0!important;margin:-1px!important;overflow:hidden!important;
    clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important
}
.dv-catalog-header__cart .dv-cart-count{
    position:absolute;right:-6px;top:-6px;z-index:3;
    min-width:21px;height:21px;padding:0 5px;display:grid;place-items:center;
    border:2px solid #fff;border-radius:999px;background:#f0393b;color:#fff;
    box-shadow:none;font-size:.62rem;font-weight:950
}
@media(hover:hover){
    .dv-catalog-header__action:hover{
        transform:translateY(-1px);box-shadow:0 7px 17px rgba(18,31,52,.10)
    }
}
.dv-catalog-header__action:focus-visible,
.dv-catalog-header__brand:focus-visible{
    outline:3px solid rgba(19,74,154,.25);outline-offset:2px
}
@media(max-width:640px){
    :root{--dv-catalog-header-height:60px}
    .dv-catalog-header__inner{width:calc(100% - 16px);gap:7px}
    .dv-catalog-header__brand{gap:6px}
    .dv-catalog-header__brand img{width:42px;height:42px}
    .dv-catalog-header__brand strong{display:none}
    .dv-catalog-header__actions{gap:4px}
    .dv-catalog-header__action{width:38px;height:38px;border-radius:11px}
    .dv-catalog-header__action svg{width:19px;height:19px}
}
</style>
"""


INSTAGRAM_ICON = """
<svg viewBox="0 0 24 24" aria-hidden="true">
  <rect x="3" y="3" width="18" height="18" rx="5"></rect>
  <circle cx="12" cy="12" r="4"></circle>
  <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"></circle>
</svg>
"""

WHATSAPP_ICON = """
<svg viewBox="0 0 24 24" aria-hidden="true">
  <path d="M20 11.5a8 8 0 0 1-11.8 7L4 20l1.4-4A8 8 0 1 1 20 11.5Z"></path>
  <path d="M9.1 8.2c.3 2.7 2 4.5 4.8 5.5"></path>
  <path d="M9.2 8.1 8.3 9.3M14 13.7l1.2-1"></path>
</svg>
"""

CART_ICON = """
<svg viewBox="0 0 24 24" aria-hidden="true">
  <path d="M3 4h2l2.2 10h10.6L20 7H7"></path>
  <circle cx="9" cy="19" r="1.6"></circle>
  <circle cx="17" cy="19" r="1.6"></circle>
</svg>
"""

CONTACT_NAV_ID = "dv-catalog-contact-links"
HEADER_ID = "dv-catalog-header"


def _header_html():
    config = ConfiguracionCatalogo.objects.first() or ConfiguracionCatalogo()
    actions = [
        (
            '<button class="dv-catalog-header__action dv-catalog-header__help" '
            'type="button" data-dv-how-buy-open aria-label="Cómo comprar" '
            'title="Cómo comprar"><span aria-hidden="true">?</span>'
            '<span class="dv-catalog-header__label">Cómo comprar</span></button>'
        )
    ]

    usuario = (config.instagram_usuario or "").strip().lstrip("@")
    if config.mostrar_instagram and usuario:
        usuario_safe = html.escape(usuario)
        url = reverse("catalogo_contacto", kwargs={"canal": "instagram"})
        actions.append(
            '<a class="dv-catalog-header__action dv-catalog-header__instagram" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
            f'aria-label="Abrir Instagram @{usuario_safe}" title="Instagram @{usuario_safe}">'
            + INSTAGRAM_ICON
            + f'<span class="dv-catalog-header__label">Instagram @{usuario_safe}</span></a>'
        )

    numero = "".join(ch for ch in (config.whatsapp_numero or "") if ch.isdigit())
    if config.mostrar_whatsapp and numero:
        url = reverse("catalogo_contacto", kwargs={"canal": "whatsapp"})
        actions.append(
            '<a class="dv-catalog-header__action dv-catalog-header__whatsapp" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
            'aria-label="Escribir por WhatsApp" title="WhatsApp">'
            + WHATSAPP_ICON
            + '<span class="dv-catalog-header__label">WhatsApp</span></a>'
        )

    actions.append(
        '<button class="dv-catalog-header__action dv-catalog-header__cart" '
        'type="button" data-dv-cart-open aria-label="Abrir carrito" title="Carrito">'
        + CART_ICON
        + '<span class="dv-cart-count" data-dv-cart-count>0</span>'
        + '<span class="dv-catalog-header__label">Carrito</span></button>'
    )

    logo_url = html.escape(static("brand/logo.png"), quote=True)
    catalogo_url = html.escape(reverse("catalogo"), quote=True)

    return (
        f'<header id="{HEADER_ID}" class="dv-catalog-header">'
        '<div class="dv-catalog-header__inner">'
        f'<a class="dv-catalog-header__brand" href="{catalogo_url}" aria-label="Ir al catálogo">'
        f'<img src="{logo_url}" alt="Doble V 3D"><strong>Doble V 3D</strong></a>'
        f'<nav id="{CONTACT_NAV_ID}" class="dv-catalog-header__actions" '
        'aria-label="Acciones del catálogo">'
        + "".join(actions)
        + "</nav></div></header>"
    )


def _header_insertado(contenido):
    return f'id="{HEADER_ID}"' in contenido


class CatalogContactMiddleware:
    """Agrega un header fijo y común a todas las pantallas públicas del catálogo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        view_name = match.view_name if match else ""

        path = getattr(request, "path_info", "") or ""
        es_catalogo_publico = (
            view_name in {
                "catalogo",
                "catalogo_legacy",
                "catalogo_kit_detalle",
                "catalogo_carrito",
                "catalogo_carrito_gracias",
            }
            or path in {"/", "/catalogo/"}
            or path.startswith("/kits/")
            or path.startswith("/carrito/")
        )

        if (
            not es_catalogo_publico
            or response.status_code != 200
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        try:
            contenido = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "dv-catalog-contact-style" not in contenido and "</head>" in contenido:
            contenido = contenido.replace(
                "</head>",
                HEADER_STYLE + "\n</head>",
                1,
            )

        if not _header_insertado(contenido):
            header = _header_html()
            contenido, cantidad = re.subn(
                r"(<body\b[^>]*>)",
                r"\1\n" + header,
                contenido,
                count=1,
                flags=re.IGNORECASE,
            )
            if cantidad == 0 and "</header>" in contenido:
                contenido = contenido.replace(
                    "</header>",
                    "</header>\n" + header,
                    1,
                )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
