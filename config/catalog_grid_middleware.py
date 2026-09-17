from config.catalog_contact_middleware import CONTACT_STYLE, _contactos_html


CATALOG_GRID_STYLE = r"""
<style id="dv-catalog-grid-density-fix">
/*
 * Cuando un filtro deja pocos resultados, conservamos el ancho habitual de
 * las tarjetas en vez de estirar el único producto a todo el contenedor.
 * auto-fill mantiene las columnas vacías; en móvil seguimos usando una sola.
 */
@media (min-width: 581px) {
    .grid {
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)) !important;
    }
}

@media (min-width: 581px) and (max-width: 900px) {
    .grid {
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)) !important;
    }
}
</style>
"""


class CatalogGridMiddleware:
    """Densidad consistente y accesos de contacto del catálogo público."""

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
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "dv-catalog-grid-density-fix" not in html and "</head>" in html:
            html = html.replace(
                "</head>",
                CATALOG_GRID_STYLE + "\n</head>",
                1,
            )

        contactos = _contactos_html()
        if contactos:
            if "dv-catalog-contact-style" not in html and "</head>" in html:
                html = html.replace(
                    "</head>",
                    CONTACT_STYLE + "\n</head>",
                    1,
                )

            if "dv-catalog-contact" not in html and "</header>" in html:
                html = html.replace(
                    "</header>",
                    contactos + "\n</header>",
                    1,
                )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
