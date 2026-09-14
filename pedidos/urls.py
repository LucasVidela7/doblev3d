from django.urls import path

from . import views


app_name = "pedidos"


urlpatterns = [

    path(
        "nuevo/",
        views.nuevo_pedido,
        name="nuevo",
    ),

    path(
        "impresiones/",
        views.impresiones_por_pedido,
        name="impresiones",
    ),

    path(
        "impresiones/productos/",
        views.impresiones_por_producto,
        name="impresiones_productos",
    ),

    path(
        "impresiones/listo/",
        views.cambiar_listo_impresion,
        name="cambiar_listo",
    ),

    path(
        "api/kit/<int:kit_id>/productos/",
        views.productos_por_kit,
        name="productos_kit",
    ),


    path(
        "<int:pedido_id>/editar/",
        views.editar_pedido,
        name="editar",
    ),

    path(
        "<int:pedido_id>/entregar/",
        views.entregar_pedido,
        name="entregar",
    ),

    path(
        "<int:pedido_id>/cancelar/",
        views.cancelar_pedido,
        name="cancelar",
    ),

    path(
        "<int:pedido_id>/eliminar/",
        views.eliminar_pedido,
        name="eliminar",
    ),

]