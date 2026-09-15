from django.urls import path

from . import views
from .precios_api import recomendar_precio_fijo


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
        "recomendacion-fija/",
        recomendar_precio_fijo,
        name="recomendacion_fija",
    ),
    path(
        "<int:kit_id>/editar/",
        views.editar_kit,
        name="editar",
    ),
]
