from django.urls import path
from . import views


app_name = "dashboard"


urlpatterns = [

    path(
        "",
        views.inicio,
        name="inicio",
    ),

    path(
        "dashboard/produccion/<int:produccion_id>/iniciar/",
        views.iniciar_produccion_dashboard,
        name="produccion_iniciar",
    ),

    path(
        "dashboard/produccion/<int:produccion_id>/estado/",
        views.cambiar_estado_produccion_dashboard,
        name="produccion_estado",
    ),

]
