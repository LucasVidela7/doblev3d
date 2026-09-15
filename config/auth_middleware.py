from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import resolve


class LoginRequiredMiddleware:
    """
    Protege la aplicación completa por defecto.

    Toda vista nueva queda cerrada automáticamente salvo las rutas
    expresamente públicas. Esto evita depender de recordar @login_required
    en cada view del sistema.
    """

    PUBLIC_URL_NAMES = {
        "login",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        match = resolve(request.path_info)

        if match.url_name in self.PUBLIC_URL_NAMES:
            return self.get_response(request)

        return redirect_to_login(
            request.get_full_path(),
            settings.LOGIN_URL,
        )
