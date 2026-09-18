from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from productos.catalogo import catalogo, catalogo_kit_detalle
from productos.catalogo_contacto import catalogo_contacto


urlpatterns = [
    # Sitio publico
    path(
        "",
        catalogo,
        name="catalogo",
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
