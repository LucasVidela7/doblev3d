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
        "<int:produccion_id>/estado/",
        views.cambiar_estado,
        name="cambiar_estado",
    ),

]