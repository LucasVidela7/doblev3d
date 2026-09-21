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
    position:relative;
    width:min(1180px,calc(100% - 24px));height:100%;margin:0 auto;
    display:grid;grid-template-columns:auto minmax(0,1fr) auto;
    align-items:center;gap:14px
}
.dv-catalog-header__nav{
    min-width:0;display:flex;align-items:center;justify-content:center;gap:4px
}
.dv-catalog-header__nav-link{
    min-height:38px;display:inline-flex;align-items:center;justify-content:center;
    padding:0 12px;border-radius:11px;color:#40506a;text-decoration:none;
    font-size:.76rem;font-weight:900;transition:.15s ease
}
.dv-catalog-header__nav-link:hover{
    background:#eef4ff;color:#134a9a
}
.dv-catalog-header__nav-link.is-active{
    background:#202328;color:#fff;border-color:#202328
}
.dv-catalog-header__withdrawal-link{
    border:1px solid #d46a6a;
    background:#fff7f7;
    color:#9b2d2d;
    font-size:.61rem;
    letter-spacing:.02em
}
.dv-catalog-header__withdrawal-link:hover{
    background:#fff0f0;color:#842222
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
    :root{--dv-catalog-header-height:102px}
    .dv-catalog-header__inner{
        width:calc(100% - 16px);height:60px;gap:7px;
        grid-template-columns:auto 1fr
    }
    .dv-catalog-header__brand{gap:6px}
    .dv-catalog-header__brand img{width:42px;height:42px}
    .dv-catalog-header__brand strong{display:none}
    .dv-catalog-header__actions{gap:4px;justify-self:end}
    .dv-catalog-header__action{width:38px;height:38px;border-radius:11px}
    .dv-catalog-header__action svg{width:19px;height:19px}
    .dv-catalog-header__nav{
        position:absolute;left:0;right:0;top:62px;
        height:34px;justify-content:stretch;gap:5px
    }
    .dv-catalog-header__nav-link{
        flex:1 1 0;min-height:34px;padding:0 7px;
        border:1px solid #e3e8ef;background:#fff;font-size:.7rem
    }
    .dv-catalog-header__nav-link.dv-catalog-header__withdrawal-link{
        position:absolute;left:0;right:0;top:39px;
        min-height:24px;border-radius:9px;
        font-size:.58rem
    }
    body:has(.dv-catalog-header__withdrawal-link){
        padding-top:128px!important
    }
    body:has(.dv-catalog-header__withdrawal-link) .toolbar{
        top:128px!important
    }
}
.dv-catalog-legal-footer{
    width:min(1180px,calc(100% - 24px));margin:30px auto 0;padding:18px 0 8px;
    border-top:1px solid #dfe5ef;color:#667085
}
.dv-catalog-legal-footer__inner{
    display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap
}
.dv-catalog-legal-footer__brand{font-size:.72rem;font-weight:900;color:#0d376f}
.dv-catalog-legal-footer__links{display:flex;flex-wrap:wrap;gap:8px 14px}
.dv-catalog-legal-footer__links a{
    color:#56657a;text-decoration:none;font-size:.68rem;font-weight:800
}
.dv-catalog-legal-footer__links a:hover{text-decoration:underline}

.dv-catalog-withdrawal-float{
    position:fixed;right:max(14px,env(safe-area-inset-right));
    bottom:max(14px,env(safe-area-inset-bottom));z-index:76;
    min-height:44px;display:inline-flex;align-items:center;justify-content:center;gap:8px;
    padding:0 14px;border:1px solid #b92f36;border-radius:14px;
    background:#c63838;color:#fff;text-decoration:none;
    box-shadow:0 12px 28px rgba(117,26,31,.25);
    font-size:.68rem;font-weight:950;letter-spacing:.015em;
    white-space:nowrap;overflow:hidden;
    transition:
        min-height .24s ease,padding .24s ease,border-radius .24s ease,
        font-size .24s ease,gap .24s ease,transform .15s ease,
        box-shadow .24s ease,background .15s ease;
    -webkit-tap-highlight-color:transparent
}
.dv-catalog-withdrawal-float.is-compact{
    min-height:36px;padding:0 9px;border-radius:999px;gap:5px;
    font-size:.56rem;
    box-shadow:0 8px 20px rgba(117,26,31,.20)
}
.dv-catalog-withdrawal-float__icon{
    width:23px;height:23px;display:grid;place-items:center;flex:0 0 auto;
    border-radius:999px;background:rgba(255,255,255,.16);
    font-size:1rem;line-height:1;
    transition:width .24s ease,height .24s ease,font-size .24s ease
}
.dv-catalog-withdrawal-float.is-compact .dv-catalog-withdrawal-float__icon{
    width:20px;height:20px;font-size:.86rem
}
@media(hover:hover){
    .dv-catalog-withdrawal-float:hover{
        transform:translateY(-1px);background:#b72f35;
        box-shadow:0 15px 32px rgba(117,26,31,.3)
    }
}
.dv-catalog-withdrawal-float:focus-visible{
    outline:3px solid rgba(198,56,56,.24);outline-offset:3px
}
body:has(.dv-product-builder) .dv-catalog-withdrawal-float,
body:has(.dv-kit-builder) .dv-catalog-withdrawal-float{
    bottom:88px
}

@media(max-width:640px){
    .dv-catalog-withdrawal-float{
        right:max(10px,env(safe-area-inset-right));
        bottom:max(10px,env(safe-area-inset-bottom));
        min-height:42px;padding:0 11px;border-radius:12px;
        font-size:.61rem
    }
    .dv-catalog-withdrawal-float.is-compact{
        min-height:34px;padding:0 8px;border-radius:999px;
        gap:4px;font-size:.52rem
    }
    .dv-catalog-withdrawal-float__icon{width:21px;height:21px;font-size:.9rem}
    .dv-catalog-withdrawal-float.is-compact .dv-catalog-withdrawal-float__icon{
        width:19px;height:19px;font-size:.8rem
    }
    body:has(.dv-product-builder) .dv-catalog-withdrawal-float,
    body:has(.dv-kit-builder) .dv-catalog-withdrawal-float{
        bottom:88px
    }
    .dv-catalog-legal-footer{margin-top:22px;padding-bottom:72px}
    .dv-catalog-legal-footer__inner{display:grid;grid-template-columns:1fr}
    .dv-catalog-legal-footer__links{display:grid;grid-template-columns:1fr 1fr}
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


def _header_html(view_name=""):
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
    productos_url = html.escape(reverse("catalogo_productos"), quote=True)
    kits_url = html.escape(reverse("catalogo_kits"), quote=True)

    inicio_class = " is-active" if view_name in {"catalogo", "catalogo_legacy"} else ""
    productos_class = " is-active" if view_name in {"catalogo_productos", "catalogo_producto_detalle"} else ""
    kits_class = " is-active" if view_name in {"catalogo_kits", "catalogo_kit_detalle"} else ""

    return (
        f'<header id="{HEADER_ID}" class="dv-catalog-header">'
        '<div class="dv-catalog-header__inner">'
        f'<a class="dv-catalog-header__brand" href="{catalogo_url}" aria-label="Ir al inicio">'
        f'<img src="{logo_url}" alt="Doble V 3D"><strong>Doble V 3D</strong></a>'
        '<nav class="dv-catalog-header__nav" aria-label="Secciones de la tienda">'
        f'<a class="dv-catalog-header__nav-link{inicio_class}" href="{catalogo_url}">INICIO</a>'
        f'<a class="dv-catalog-header__nav-link{productos_class}" href="{productos_url}">PRODUCTOS</a>'
        f'<a class="dv-catalog-header__nav-link{kits_class}" href="{kits_url}">KITS</a>'
        + '</nav>'
        f'<nav id="{CONTACT_NAV_ID}" class="dv-catalog-header__actions" '
        'aria-label="Acciones del catálogo">'
        + "".join(actions)
        + "</nav></div></header>"
    )



def _legal_footer_html(view_name=""):
    terminos_url = html.escape(
        reverse("catalogo_terminos"),
        quote=True,
    )
    privacidad_url = html.escape(
        reverse("catalogo_privacidad"),
        quote=True,
    )
    arrepentimiento_url = html.escape(
        reverse("catalogo_arrepentimiento"),
        quote=True,
    )

    mostrar_flotante = view_name in {
        "catalogo",
        "catalogo_legacy",
        "catalogo_productos",
        "catalogo_producto_detalle",
        "catalogo_kits",
        "catalogo_kit_detalle",
        "catalogo_carrito",
        "catalogo_carrito_gracias",
    }
    flotante = ""
    if mostrar_flotante:
        flotante = (
            f'<a id="dv-catalog-withdrawal-float" class="dv-catalog-withdrawal-float" '
            f'href="{arrepentimiento_url}" aria-label="Botón de arrepentimiento">'
            '<span class="dv-catalog-withdrawal-float__icon" aria-hidden="true">↩</span>'
            '<span>BOTÓN DE ARREPENTIMIENTO</span></a>'
            '<script>(function(){'
            'var b=document.getElementById("dv-catalog-withdrawal-float");'
            'if(!b)return;'
            'var t=null;'
            'function compact(){b.classList.add("is-compact");}'
            'function expand(){clearTimeout(t);b.classList.remove("is-compact");}'
            'function later(){clearTimeout(t);t=setTimeout(compact,900);}'
            't=setTimeout(compact,5000);'
            'b.addEventListener("pointerenter",expand);'
            'b.addEventListener("pointerleave",later);'
            'b.addEventListener("focus",expand);'
            'b.addEventListener("blur",later);'
            '})();</script>'
        )

    contenido = (
        flotante
        + '<footer class="dv-catalog-legal-footer" id="dv-catalog-legal-footer">'
        '<div class="dv-catalog-legal-footer__inner">'
        '<div class="dv-catalog-legal-footer__brand">Doble V 3D · Catálogo online</div>'
        '<nav class="dv-catalog-legal-footer__links" aria-label="Información legal">'
        f'<a href="{terminos_url}">Términos de compra</a>'
        f'<a href="{privacidad_url}">Privacidad</a>'
        f'<a href="{arrepentimiento_url}">Cambios y arrepentimiento</a>'
        '</nav></div></footer>'
    )

    return contenido


def _legal_insertado(contenido):
    return 'id="dv-catalog-legal-footer"' in contenido


def _header_insertado(contenido):
    return f'id="{HEADER_ID}"' in contenido


# Compatibilidad con CatalogGridMiddleware, que históricamente reutiliza
# estos helpers para evitar duplicar la UI del catálogo.
CONTACT_STYLE = HEADER_STYLE
_contactos_html = _header_html
_contactos_insertados = _header_insertado


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
                "catalogo_productos",
                "catalogo_producto_detalle",
                "catalogo_kits",
                "catalogo_kit_detalle",
                "catalogo_carrito",
                "catalogo_carrito_gracias",
                "catalogo_terminos",
                "catalogo_privacidad",
                "catalogo_arrepentimiento",
                "catalogo_arrepentimiento_gracias",
            }
            or path in {"/", "/catalogo/", "/productos/", "/kits/"}
            or path.startswith("/kits/")
            or path.startswith("/carrito/")
            or path.startswith("/terminos/")
            or path.startswith("/privacidad/")
            or path.startswith("/arrepentimiento/")
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
            header = _header_html(view_name)
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

        if not _legal_insertado(contenido):
            legal = _legal_footer_html(view_name)
            if "</body>" in contenido:
                contenido = contenido.replace(
                    "</body>",
                    legal + "\n</body>",
                    1,
                )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
