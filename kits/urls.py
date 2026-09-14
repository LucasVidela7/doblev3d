from django.urls import path

from . import views


app_name = "kits"


urlpatterns = [
    path(
        "",
        views.lista_kits,
        name="lista",
    ),
    path(
        "nuevo/",
        views.nuevo_kit,
        name="nuevo",
    ),
    path(
        "<int:kit_id>/editar/",
        views.editar_kit,
        name="editar",
    ),
]
