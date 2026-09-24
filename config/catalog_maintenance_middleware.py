from django.conf import settings
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
        "catalogo_categoria",
        "catalogo_producto_detalle",
        "catalogo_producto_legacy",
        "catalogo_kits",
        "catalogo_kit_detalle",
        "catalogo_kit_legacy",
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
        mantenimiento_forzado = bool(
            getattr(settings, "CATALOGO_MANTENIMIENTO", False)
        )
        mantenimiento_activo = (
            mantenimiento_forzado
            or bool(config and not config.catalogo_activo)
        )

        if not mantenimiento_activo:
            return self.get_response(request)

        mensaje_mantenimiento = (
            config.mensaje_mantenimiento
            if config and config.mensaje_mantenimiento
            else (
                "Estamos haciendo unos ajustes en la tienda. "
                "Volvé a visitarnos en unos minutos."
            )
        )

        usuario = getattr(request, "user", None)
        es_admin = bool(
            usuario
            and usuario.is_authenticated
            and (usuario.is_staff or usuario.is_superuser)
        )

        if es_admin:
            request.catalogo_en_mantenimiento = True
            request.catalogo_mantenimiento_mensaje = (
                mensaje_mantenimiento
            )
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
                "mensaje_mantenimiento": mensaje_mantenimiento,
            },
            status=503,
        )
