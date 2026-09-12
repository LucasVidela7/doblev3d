from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [

    path(
        "nuevo/",
        views.nuevo_pedido,
        name="nuevo"
    ),

    path(
        "impresiones/",
        views.impresiones_por_pedido,
        name="impresiones"
    ),

    path(
        "impresiones/listo/",
        views.cambiar_listo_impresion,
        name="cambiar_listo_impresion"
    ),

    path(
        "api/kit/<int:kit_id>/productos/",
        views.productos_por_kit,
        name="productos_por_kit"
    ),
    path(
        "impresiones/productos/",
        views.impresiones_por_producto,
        name="impresiones_por_producto"
    ),

]
