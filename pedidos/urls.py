from django.urls import path

from . import (
    acciones_impresion,
    acciones_pedido,
    detalle_views,
    historial_views,
    pedido_form_views,
    preparacion_views,
    precios_api,
    presupuesto_views,
    solicitud_web_views,
    views,
)
from .impresiones_corregidas import impresiones_por_producto
from .planificacion_producto import planificar_impresion_producto


app_name = "pedidos"


urlpatterns = [

    path(
        "nuevo/",
        presupuesto_views.nuevo_presupuesto,
        name="nuevo",
    ),

    path(
        "presupuestos/",
        presupuesto_views.lista_presupuestos,
        name="presupuestos",
    ),

    path(
        "solicitudes-web/",
        solicitud_web_views.lista_solicitudes_web,
        name="solicitudes_web",
    ),

    path(
        "solicitudes-web/<int:solicitud_id>/",
        solicitud_web_views.detalle_solicitud_web,
        name="solicitud_web_detalle",
    ),

    path(
        "solicitudes-web/<int:solicitud_id>/contactada/",
        solicitud_web_views.marcar_contactada,
        name="solicitud_web_contactada",
    ),

    path(
        "solicitudes-web/<int:solicitud_id>/rechazar/",
        solicitud_web_views.rechazar_solicitud_web,
        name="solicitud_web_rechazar",
    ),

    path(
        "solicitudes-web/<int:solicitud_id>/convertir/",
        solicitud_web_views.convertir_solicitud_web,
        name="solicitud_web_convertir",
    ),

    path(
        "presupuestos/<int:presupuesto_id>/",
        presupuesto_views.detalle_presupuesto,
        name="presupuesto_detalle",
    ),

    path(
        "presupuestos/<int:presupuesto_id>/editar/",
        presupuesto_views.editar_presupuesto,
        name="presupuesto_editar",
    ),

    path(
        "presupuestos/<int:presupuesto_id>/aprobar/",
        presupuesto_views.aprobar_presupuesto,
        name="presupuesto_aprobar",
    ),

    path(
        "presupuestos/<int:presupuesto_id>/rechazar/",
        presupuesto_views.rechazar_presupuesto,
        name="presupuesto_rechazar",
    ),

    path(
        "impresiones/",
        preparacion_views.impresiones_por_pedido,
        name="impresiones",
    ),

    path(
        "impresiones/cancelados/",
        historial_views.pedidos_cancelados,
        name="cancelados",
    ),

    path(
        "impresiones/<int:pedido_id>/iniciar-preparacion/",
        preparacion_views.iniciar_preparacion,
        name="iniciar_preparacion",
    ),

    path(
        "impresiones/<int:pedido_id>/liberar-preparacion/",
        preparacion_views.liberar_preparacion,
        name="liberar_preparacion",
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
        historial_views.pagos,
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
        acciones_impresion.cambiar_listo_impresion,
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
        "<int:pedido_id>/preparacion/",
        detalle_views.cambiar_preparacion,
        name="cambiar_preparacion",
    ),

    path(
        "<int:pedido_id>/fecha-entrega/",
        detalle_views.actualizar_fecha_entrega,
        name="actualizar_fecha_entrega",
    ),


    path(
        "<int:pedido_id>/",
        detalle_views.detalle_pedido,
        name="detalle",
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
