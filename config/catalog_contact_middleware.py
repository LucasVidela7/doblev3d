import html
from urllib.parse import quote

from productos.models import ConfiguracionCatalogo


CONTACT_STYLE = r"""
<style id="dv-catalog-contact-style">
.dv-catalog-contact{
    margin-left:auto;
    display:flex;
    align-items:center;
    justify-content:flex-end;
    gap:8px;
    flex-wrap:wrap;
}
.dv-catalog-contact__link{
    min-height:42px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    gap:8px;
    padding:0 13px;
    border:1px solid #dfe5ef;
    border-radius:999px;
    background:rgba(255,255,255,.9);
    color:#0d376f;
    text-decoration:none;
    font-size:.78rem;
    font-weight:800;
    box-shadow:0 5px 16px rgba(19,74,154,.06);
    transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease;
    -webkit-tap-highlight-color:transparent;
}
.dv-catalog-contact__link svg{
    width:18px;
    height:18px;
    flex:0 0 auto;
    fill:none;
    stroke:currentColor;
    stroke-width:2;
    stroke-linecap:round;
    stroke-linejoin:round;
}
.dv-catalog-contact__link--instagram:hover{
    border-color:rgba(240,57,59,.42);
    color:#cf2730;
}
.dv-catalog-contact__link--whatsapp{
    color:#1d6d47;
}
.dv-catalog-contact__link--whatsapp:hover{
    border-color:rgba(29,109,71,.38);
    box-shadow:0 7px 20px rgba(29,109,71,.10);
}
@media(hover:hover){
    .dv-catalog-contact__link:hover{transform:translateY(-1px)}
}
@media(max-width:640px){
    .topbar{
        gap:10px!important;
        flex-wrap:wrap;
    }
    .dv-catalog-contact{
        margin-left:auto;
        gap:6px;
    }
    .dv-catalog-contact__link{
        width:42px;
        min-height:42px;
        padding:0;
    }
    .dv-catalog-contact__label{display:none}
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

CONTACT_NAV_ID = "dv-catalog-contact-links"


def _contactos_html():
    config = ConfiguracionCatalogo.objects.first() or ConfiguracionCatalogo()
    links = []

    usuario = (config.instagram_usuario or "").strip().lstrip("@")
    if config.mostrar_instagram and usuario:
        usuario_safe = html.escape(usuario)
        url = f"https://www.instagram.com/{quote(usuario, safe='')}/"
        links.append(
            '<a class="dv-catalog-contact__link dv-catalog-contact__link--instagram" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
            f'aria-label="Abrir Instagram @{usuario_safe}">'
            + INSTAGRAM_ICON
            + f'<span class="dv-catalog-contact__label">@{usuario_safe}</span></a>'
        )

    numero = "".join(ch for ch in (config.whatsapp_numero or "") if ch.isdigit())
    if config.mostrar_whatsapp and numero:
        mensaje = (config.whatsapp_mensaje or "").strip()
        url = f"https://wa.me/{numero}"
        if mensaje:
            url += f"?text={quote(mensaje)}"
        links.append(
            '<a class="dv-catalog-contact__link dv-catalog-contact__link--whatsapp" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
            'aria-label="Escribir por WhatsApp">'
            + WHATSAPP_ICON
            + '<span class="dv-catalog-contact__label">WhatsApp</span></a>'
        )

    if not links:
        return ""

    return (
        f'<nav id="{CONTACT_NAV_ID}" class="dv-catalog-contact" '
        'aria-label="Contacto y redes sociales">'
        + "".join(links)
        + "</nav>"
    )


def _contactos_insertados(contenido):
    return f'id="{CONTACT_NAV_ID}"' in contenido


class CatalogContactMiddleware:
    """Agrega al catálogo los accesos sociales definidos desde Django Admin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        view_name = match.view_name if match else ""

        if (
            view_name not in {"catalogo", "catalogo_legacy"}
            or response.status_code != 200
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        try:
            contenido = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        contactos = _contactos_html()
        if not contactos:
            return response

        if "dv-catalog-contact-style" not in contenido and "</head>" in contenido:
            contenido = contenido.replace(
                "</head>",
                CONTACT_STYLE + "\n</head>",
                1,
            )

        if not _contactos_insertados(contenido) and "</header>" in contenido:
            contenido = contenido.replace(
                "</header>",
                contactos + "\n</header>",
                1,
            )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
