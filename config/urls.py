from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from productos.catalogo import catalogo


urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path(
        "catalogo/",
        catalogo,
        name="catalogo",
    ),

    path(
        "",
        include("dashboard.urls"),
    ),

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "productos/",
        include("productos.urls"),
    ),

    path(
        "kits/",
        include("kits.urls"),
    ),

    path(
        "pedidos/",
        include("pedidos.urls"),
    ),

    path(
        "produccion/",
        include("produccion.urls"),
    ),

    path(
        "clientes/",
        include("clientes.urls"),
    ),

    path(
        "calculadora/",
        include("calculadora.urls"),
    ),
]
