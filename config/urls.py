from django.contrib import admin
from django.urls import include, path

urlpatterns = [

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
        "pedidos/",
        include("pedidos.urls"),
    ),

    path(
        "produccion/",
        include("produccion.urls"),
    ),
    path(
        "clientes/",
        include("clientes.urls")
    ),

]
