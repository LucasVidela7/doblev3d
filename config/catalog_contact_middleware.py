import html

from django.urls import reverse

from productos.models import ConfiguracionCatalogo


CONTACT_STYLE = r"""
<style id="dv-catalog-contact-style">
.dv-catalog-contact{
    position:fixed;
    right:clamp(14px,2vw,24px);
    bottom:calc(18px + env(safe-area-inset-bottom, 0px));
    z-index:80;
    display:flex;
    flex-direction:column;
    align-items:flex-end;
    gap:10px;
    pointer-events:none;
}
.dv-catalog-contact__link{
    width:56px;
    height:56px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border:0;
    border-radius:50%;
    color:#fff;
    text-decoration:none;
    box-shadow:0 10px 28px rgba(14,31,58,.20);
    transition:transform .18s ease,box-shadow .18s ease,filter .18s ease;
    -webkit-tap-highlight-color:transparent;
    pointer-events:auto;
}
.dv-catalog-contact__link svg{
    width:27px;
    height:27px;
    flex:0 0 auto;
    fill:none;
    stroke:currentColor;
    stroke-width:2;
    stroke-linecap:round;
    stroke-linejoin:round;
}
.dv-catalog-contact__link--instagram{
    background:linear-gradient(145deg,#5b51d8 0%,#c13584 45%,#f77737 100%);
}
.dv-catalog-contact__link--whatsapp{
    background:#25d366;
}
.dv-catalog-contact__label{
    position:absolute!important;
    width:1px!important;
    height:1px!important;
    padding:0!important;
    margin:-1px!important;
    overflow:hidden!important;
    clip:rect(0,0,0,0)!important;
    white-space:nowrap!important;
    border:0!important;
}
@media(hover:hover){
    .dv-catalog-contact__link:hover{
        transform:translateY(-2px) scale(1.035);
        box-shadow:0 14px 34px rgba(14,31,58,.25);
        filter:saturate(1.06);
    }
}
.dv-catalog-contact__link:focus-visible{
    outline:3px solid rgba(19,74,154,.30);
    outline-offset:3px;
}
@media(max-width:640px){
    .dv-catalog-contact{
        right:12px;
        bottom:calc(14px + env(safe-area-inset-bottom, 0px));
        gap:8px;
    }
    .dv-catalog-contact__link{
        width:50px;
        height:50px;
    }
    .dv-catalog-contact__link svg{
        width:24px;
        height:24px;
    }
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
        url = reverse("catalogo_contacto", kwargs={"canal": "instagram"})
        links.append(
            '<a class="dv-catalog-contact__link dv-catalog-contact__link--instagram" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
            f'aria-label="Abrir Instagram @{usuario_safe}" title="Instagram @{usuario_safe}">'
            + INSTAGRAM_ICON
            + f'<span class="dv-catalog-contact__label">Instagram @{usuario_safe}</span></a>'
        )

    numero = "".join(ch for ch in (config.whatsapp_numero or "") if ch.isdigit())
    if config.mostrar_whatsapp and numero:
        url = reverse("catalogo_contacto", kwargs={"canal": "whatsapp"})
        links.append(
            '<a class="dv-catalog-contact__link dv-catalog-contact__link--whatsapp" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
            'aria-label="Escribir por WhatsApp" title="WhatsApp">'
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
