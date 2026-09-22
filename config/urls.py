from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from config.health import healthcheck

from productos.catalogo import (
    catalogo_404,
    catalogo,
    catalogo_kits,
    catalogo_productos,
    catalogo_producto_detalle,
    catalogo_kit_detalle,
)
from productos.catalogo_contacto import catalogo_contacto
from productos.legal import (
    arrepentimiento,
    arrepentimiento_gracias,
    privacidad,
    terminos_compra,
)
from productos.carrito import (
    carrito_checkout,
    carrito_gracias,
    carrito_precios,
    solicitud_publica,
)


handler404 = catalogo_404


urlpatterns = [
    path("healthz/", healthcheck, name="healthcheck"),
    path("metricas/", include("metricas.urls")),
    # Sitio publico
    path(
        "",
        catalogo,
        name="catalogo",
    ),

    # Tienda pública separada por tipo de contenido.
    path(
        "productos/",
        catalogo_productos,
        name="catalogo_productos",
    ),
    path(
        "kits/",
        catalogo_kits,
        name="catalogo_kits",
    ),
    path(
        "productos/<int:producto_id>/",
        catalogo_producto_detalle,
        name="catalogo_producto_detalle",
    ),

    # Alias historico para no romper URLs ya compartidas.
    path(
        "catalogo/",
        catalogo,
        name="catalogo_legacy",
    ),

    # Detalle público de kits del catálogo.
    path(
        "kits/<int:kit_id>/",
        catalogo_kit_detalle,
        name="catalogo_kit_detalle",
    ),

    # Información legal y derechos del consumidor.
    path(
        "terminos/",
        terminos_compra,
        name="catalogo_terminos",
    ),
    path(
        "privacidad/",
        privacidad,
        name="catalogo_privacidad",
    ),
    path(
        "arrepentimiento/",
        arrepentimiento,
        name="catalogo_arrepentimiento",
    ),
    path(
        "arrepentimiento/gracias/",
        arrepentimiento_gracias,
        name="catalogo_arrepentimiento_gracias",
    ),

    # Carrito y solicitud pública de presupuesto.
    path(
        "carrito/",
        carrito_checkout,
        name="catalogo_carrito",
    ),
    path(
        "carrito/precios/",
        carrito_precios,
        name="catalogo_carrito_precios",
    ),
    path(
        "carrito/gracias/",
        carrito_gracias,
        name="catalogo_carrito_gracias",
    ),
    path(
        "solicitud/<uuid:token>/",
        solicitud_publica,
        name="solicitud_publica",
    ),

    # Los enlaces sociales pasan por el sistema para registrar el click antes
    # de redirigir al destino externo configurado desde el admin.
    path(
        "contacto/<str:canal>/",
        catalogo_contacto,
        name="catalogo_contacto",
    ),

    # Sistema interno
    path(
        "gestion/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),

    path(
        "gestion/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path(
        "gestion/",
        include("dashboard.urls"),
    ),

    path(
        "gestion/admin/",
        admin.site.urls,
    ),

    path(
        "gestion/productos/",
        include("productos.urls"),
    ),

    path(
        "gestion/kits/",
        include("kits.urls"),
    ),

    path(
        "gestion/pedidos/",
        include("pedidos.urls"),
    ),

    path(
        "gestion/produccion/",
        include("produccion.urls"),
    ),

    path(
        "gestion/clientes/",
        include("clientes.urls"),
    ),

    path(
        "gestion/calculadora/",
        include("calculadora.urls"),
    ),
]
