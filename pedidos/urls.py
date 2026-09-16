from django.urls import path

from . import acciones_pedido, pedido_form_views, precios_api, views
from .impresiones_compuestas import (
    impresiones_por_producto,
    planificar_impresion_producto,
)


app_name = "pedidos"


urlpatterns = [

    path(
        "nuevo/",
        pedido_form_views.nuevo_pedido,
        name="nuevo",
    ),

    path(
        "impresiones/",
        views.impresiones_por_pedido,
        name="impresiones",
    ),

    path(
        "impresiones/productos/",
        impresiones_por_producto,
        name="impresiones_productos",
    ),

    path(
        "impresiones/productos/planificar/",
        planificar_impresion_producto,
        name="planificar_impresion_producto",
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
        "finanzas/caja/actualizar/",
        views.actualizar_saldo_caja,
        name="actualizar_saldo_caja",
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
        pedido_form_views.productos_por_kit,
        name="productos_kit",
    ),

    path(
        "api/precio-producto/",
        precios_api.precio_producto,
        name="precio_producto",
    ),

    path(
        "api/precio-kits-volumen/",
        precios_api.precio_kits_volumen,
        name="precio_kits_volumen",
    ),

    path(
        "<int:pedido_id>/pago/",
        views.registrar_pago,
        name="registrar_pago",
    ),

    path(
        "<int:pedido_id>/editar/",
        acciones_pedido.editar_pedido,
        name="editar",
    ),

    path(
        "<int:pedido_id>/entregar/",
        acciones_pedido.entregar_pedido,
        name="entregar",
    ),

    path(
        "<int:pedido_id>/cancelar/",
        acciones_pedido.cancelar_pedido,
        name="cancelar",
    ),

    path(
        "<int:pedido_id>/eliminar/",
        acciones_pedido.eliminar_pedido,
        name="eliminar",
    ),

]
