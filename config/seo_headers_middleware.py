from django.conf import settings
from django.urls import Resolver404, resolve


class SEOHeadersMiddleware:
    NOINDEX_NAMES = {
        "catalogo_carrito",
        "catalogo_carrito_precios",
        "catalogo_carrito_gracias",
        "solicitud_publica",
        "pedido_publico",
        "catalogo_arrepentimiento",
        "catalogo_arrepentimiento_gracias",
        "catalogo_producto_social_preview",
        "catalogo_kit_social_preview",
        "healthcheck",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # QA/staging nunca debe competir con el dominio productivo.
        if getattr(settings, "APP_ENV", "") != "production":
            response["X-Robots-Tag"] = "noindex, nofollow"
            return response

        try:
            match = resolve(request.path_info)
        except Resolver404:
            return response

        if (
            match.url_name in self.NOINDEX_NAMES
            or request.path_info.startswith("/gestion/")
            or request.path_info.startswith("/metricas/")
        ):
            response["X-Robots-Tag"] = "noindex, nofollow"

        return response
