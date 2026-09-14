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
        "pagos/",
        views.pagos,
        name="pagos",
    ),

    path(
        "finanzas/",
        views.finanzas,
        name="finanzas",
    ),

    path(
        "gastos/nuevo/",
        views.registrar_gasto,
        name="registrar_gasto",
    ),

    path(
        "gastos/<int:gasto_id>/eliminar/",
        views.eliminar_gasto,
        name="eliminar_gasto",
    ),

    path(
        "gastos/cuotas/<int:cuota_id>/estado/",
        views.cambiar_estado_cuota,
        name="cambiar_estado_cuota",
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
        "api/precio-producto/",
        views.precio_producto,
        name="precio_producto",
    ),


    path(
        "<int:pedido_id>/pago/",
        views.registrar_pago,
        name="registrar_pago",
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