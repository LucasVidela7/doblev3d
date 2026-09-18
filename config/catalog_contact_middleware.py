import html

from django.urls import reverse

from productos.models import ConfiguracionCatalogo


CONTACT_STYLE = r"""
<style id="dv-catalog-contact-style">
.dv-catalog-contact{
    position:fixed;
    right:clamp(14px,2vw,24px);
    bottom:calc(82px + env(safe-area-inset-bottom, 0px));
    z-index:80;
    display:flex;
    flex-direction:column;
    align-items:center;
    gap:4px;
    padding:6px;
    border:1px solid rgba(19,74,154,.12);
    border-radius:999px;
    background:rgba(255,255,255,.94);
    box-shadow:0 12px 30px rgba(14,31,58,.16);
    backdrop-filter:blur(10px);
    -webkit-backdrop-filter:blur(10px);
    transform:translateZ(0);
    backface-visibility:hidden;
    contain:layout paint;
    pointer-events:auto;
}
.dv-catalog-contact__link{
    width:44px;
    height:44px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    flex:0 0 auto;
    border:0;
    border-radius:50%;
    color:#fff;
    text-decoration:none;
    box-shadow:none;
    transition:filter .16s ease,background .16s ease;
    -webkit-tap-highlight-color:transparent;
    pointer-events:auto;
}
button.dv-catalog-contact__link{
    padding:0;
    font:inherit;
    cursor:pointer;
}
.dv-catalog-contact__link svg{
    width:23px;
    height:23px;
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
.dv-catalog-contact__help{
    background:#eef4ff;
    color:#134a9a;
    font-size:1.02rem;
    font-weight:950;
}
.dv-catalog-contact__help[hidden]{
    display:none!important;
}
.dv-catalog-contact__separator{
    width:26px;
    height:1px;
    margin:1px 0;
    background:#e4e9f1;
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
        filter:saturate(1.08) brightness(.98);
    }
}
.dv-catalog-contact__link:focus-visible{
    outline:3px solid rgba(19,74,154,.30);
    outline-offset:2px;
}
@media(max-width:640px){
    .dv-catalog-contact{
        right:12px;
        bottom:calc(70px + env(safe-area-inset-bottom, 0px));
        gap:3px;
        padding:5px;
    }
    .dv-catalog-contact__link{
        width:42px;
        height:42px;
    }
    .dv-catalog-contact__link svg{
        width:22px;
        height:22px;
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

        contactos = _contactos_html()
        if not contactos:
            return response

        if "dv-catalog-contact-style" not in contenido and "</head>" in contenido:
            contenido = contenido.replace(
                "</head>",
                CONTACT_STYLE + "\n</head>",
                1,
            )

        if not _contactos_insertados(contenido):
            if "</body>" in contenido:
                contenido = contenido.replace(
                    "</body>",
                    contactos + "\n</body>",
                    1,
                )
            elif "</header>" in contenido:
                contenido = contenido.replace(
                    "</header>",
                    contactos + "\n</header>",
                    1,
                )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
