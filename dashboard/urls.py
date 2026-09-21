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
        "configuracion/",
        views.configuracion,
        name="configuracion",
    ),
    path(
        "configuracion/arrepentimiento/<int:solicitud_id>/resolver/",
        views.resolver_arrepentimiento,
        name="arrepentimiento_resolver",
    ),

    path(
        "sw.js",
        views.push_service_worker,
        name="push_service_worker",
    ),

    path(
        "push/suscribir/",
        views.push_suscribir,
        name="push_suscribir",
    ),

    path(
        "push/desuscribir/",
        views.push_desuscribir,
        name="push_desuscribir",
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
