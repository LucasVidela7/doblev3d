from django.http import JsonResponse
from django.shortcuts import render
from django.urls import Resolver404, resolve

from productos.models import ConfiguracionCatalogo


class CatalogMaintenanceMiddleware:
    """
    Permite apagar toda la tienda pública desde Gestión sin afectar
    ninguna pantalla interna.
    """

    CATALOG_URL_NAMES = {
        "catalogo",
        "catalogo_legacy",
        "catalogo_productos",
        "catalogo_kits",
        "catalogo_kit_detalle",
        "catalogo_carrito",
        "catalogo_carrito_precios",
        "catalogo_carrito_gracias",
        "catalogo_contacto",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)

        if match.url_name not in self.CATALOG_URL_NAMES:
            return self.get_response(request)

        config = ConfiguracionCatalogo.objects.first()
        if not config or config.catalogo_activo:
            return self.get_response(request)

        if match.url_name == "catalogo_carrito_precios":
            return JsonResponse(
                {
                    "ok": False,
                    "mensaje": "El catálogo está temporalmente en mantenimiento.",
                    "mantenimiento": True,
                },
                status=503,
            )

        return render(
            request,
            "productos/catalogo_mantenimiento.html",
            {
                "mensaje_mantenimiento": config.mensaje_mantenimiento,
            },
            status=503,
        )
