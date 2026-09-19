from django.urls import path

from . import views


app_name = "produccion"


urlpatterns = [
    path(
        "",
        views.lista_produccion,
        name="lista",
    ),
    path(
        "nueva/",
        views.nueva_produccion,
        name="nueva",
    ),
    path(
        "accion-rapida/",
        views.accion_rapida_necesidad,
        name="accion_rapida",
    ),
    path(
        "api/tiempo-recomendado/",
        views.tiempo_recomendado,
        name="tiempo_recomendado",
    ),
    path(
        "<int:produccion_id>/iniciar/",
        views.iniciar_produccion,
        name="iniciar",
    ),
    path(
        "<int:produccion_id>/repetir/",
        views.repetir_produccion,
        name="repetir",
    ),
    path(
        "<int:produccion_id>/estado/",
        views.cambiar_estado,
        name="cambiar_estado",
    ),
]
