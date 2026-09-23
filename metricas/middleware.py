from django.templatetags.static import static


PAGINAS = {
    "catalogo": "inicio",
    "catalogo_legacy": "inicio",
    "catalogo_productos": "productos",
    "catalogo_producto_detalle": "producto_detalle",
    "catalogo_kits": "kits",
    "catalogo_kit_detalle": "kit_detalle",
    "catalogo_carrito": "checkout",
    "catalogo_carrito_gracias": "confirmacion",
    "catalogo_terminos": "terminos",
    "catalogo_privacidad": "privacidad",
    "catalogo_arrepentimiento": "arrepentimiento",
    "catalogo_arrepentimiento_gracias": "arrepentimiento_gracias",
}


class CatalogMetricsMiddleware:
    """Inyecta el tracker propio sólo en páginas públicas del catálogo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        view_name = match.view_name if match else ""

        if (
            view_name not in PAGINAS
            or response.status_code != 200
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
            or getattr(request.user, "is_authenticated", False)
        ):
            return response

        try:
            contenido = response.content.decode(
                response.charset or "utf-8"
            )
        except (AttributeError, UnicodeDecodeError):
            return response

        if "data-dv-metrics-script" in contenido:
            return response

        contenido_tipo = ""
        contenido_id = ""
        kwargs = getattr(match, "kwargs", {}) or {}

        if view_name == "catalogo_producto_detalle":
            contenido_tipo = "PRODUCTO"
            contenido_id = kwargs.get("producto_id", "")
        elif view_name == "catalogo_kit_detalle":
            contenido_tipo = "KIT"
            contenido_id = kwargs.get("kit_id", "")

        script = (
            '<script data-dv-metrics-script '
            f'data-page-kind="{PAGINAS[view_name]}" '
            f'data-content-kind="{contenido_tipo}" '
            f'data-content-id="{contenido_id}" '
            f'src="{static("metricas/catalog_metrics.js")}" defer></script>'
        )

        if "</body>" in contenido:
            contenido = contenido.replace(
                "</body>",
                script + "\n</body>",
                1,
            )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
