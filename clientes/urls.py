from django.urls import path

from . import views


app_name = "clientes"


urlpatterns = [
    path(
        "",
        views.lista_clientes,
        name="lista",
    ),
    path(
        "<int:cliente_id>/",
        views.detalle_cliente,
        name="detalle",
    ),
    path(
        "<int:cliente_id>/historial/",
        views.historial_cliente,
        name="historial",
    ),
    path(
        "<int:cliente_id>/whatsapp/",
        views.whatsapp_cliente,
        name="whatsapp",
    ),
    path(
        "<int:cliente_id>/fusionar/",
        views.fusionar_cliente,
        name="fusionar",
    ),
]
