from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import Resolver404, resolve


class LoginRequiredMiddleware:
    """
    Protege la aplicación completa por defecto.

    Toda vista nueva queda cerrada automáticamente salvo las rutas
    expresamente públicas. Esto evita depender de recordar @login_required
    en cada view del sistema.
    """

    PUBLIC_URL_NAMES = {
        "login",
        "catalogo",
        "catalogo_legacy",
        "catalogo_productos",
        "catalogo_categoria",
        "catalogo_producto_detalle",
        "catalogo_producto_legacy",
        "catalogo_kits",
        "catalogo_kit_detalle",
        "catalogo_kit_legacy",
        "catalogo_producto_social_preview",
        "catalogo_kit_social_preview",
        "catalogo_carrito",
        "catalogo_carrito_precios",
        "catalogo_carrito_gracias",
        "solicitud_publica",
        "pedido_publico",
        "catalogo_contacto",
        "catalogo_terminos",
        "catalogo_privacidad",
        "catalogo_arrepentimiento",
        "catalogo_arrepentimiento_gracias",
        "healthcheck",
        "robots_txt",
        "sitemap_xml",
        "evento",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        try:
            match = resolve(request.path_info)
        except Resolver404:
            # Las rutas internas inexistentes siguen detrás del login.
            # En el sitio público dejamos que Django llegue al handler 404
            # del catálogo para no sacar al cliente de la experiencia de tienda.
            if request.path_info.startswith("/gestion/"):
                return redirect_to_login(
                    request.get_full_path(),
                    settings.LOGIN_URL,
                )
            return self.get_response(request)

        if match.url_name in self.PUBLIC_URL_NAMES:
            return self.get_response(request)

        return redirect_to_login(
            request.get_full_path(),
            settings.LOGIN_URL,
        )
