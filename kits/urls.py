from django.urls import path

from . import views
from .listado import lista_kits
from .precios_api import (
    recomendar_precio_fijo,
    recomendar_precio_libre,
)


app_name = "kits"


urlpatterns = [
    path(
        "",
        lista_kits,
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
        "recomendacion-libre/",
        recomendar_precio_libre,
        name="recomendacion_libre",
    ),
    path(
        "<int:kit_id>/",
        views.detalle_kit,
        name="detalle",
    ),
    path(
        "<int:kit_id>/editar/",
        views.editar_kit,
        name="editar",
    ),
]
