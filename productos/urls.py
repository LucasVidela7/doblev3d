from django.urls import path

from . import views
from . import imagenes_views
from . import imagenes_masivas
from . import insumos
from . import compras_insumos
from . import archivos_impresion
from . import modificacion_masiva
from .tipos import categorias_seo, crear_tipo_producto


app_name = "productos"


urlpatterns = [
    path(
        "",
        views.lista,
        name="lista",
    ),
    path(
        "nuevo/",
        views.nuevo,
        name="nuevo",
    ),
    path(
        "insumos/",
        insumos.lista,
        name="insumos",
    ),
    path(
        "insumos/nuevo/",
        insumos.nuevo,
        name="insumo_nuevo",
    ),
    path(
        "insumos/<int:insumo_id>/editar/",
        insumos.editar,
        name="insumo_editar",
    ),
    path(
        "insumos/<int:insumo_id>/activo/",
        insumos.cambiar_activo,
        name="insumo_activo",
    ),
    path(
        "insumos/compras/",
        compras_insumos.lista_compras,
        name="compras_insumos",
    ),
    path(
        "insumos/compras/registrar/",
        compras_insumos.registrar_compra,
        name="compra_insumo_registrar",
    ),
    path(
        "imagenes/carga-masiva/",
        imagenes_masivas.carga_masiva,
        name="imagenes_masivas",
    ),
    path(
        "modificacion-masiva/",
        modificacion_masiva.modificacion_masiva,
        name="modificacion_masiva",
    ),
    path(
        "categorias-seo/",
        categorias_seo,
        name="categorias_seo",
    ),
    path(
        "api/tipos/crear/",
        crear_tipo_producto,
        name="crear_tipo",
    ),
    path(
        "<int:producto_id>/",
        views.detalle,
        name="detalle",
    ),
    path(
        "<int:producto_id>/editar/",
        views.editar,
        name="editar",
    ),
    path(
        "<int:producto_id>/archivos-impresion/subir/",
        archivos_impresion.subir,
        name="archivo_impresion_subir",
    ),
    path(
        "<int:producto_id>/archivos-impresion/<int:archivo_id>/descargar/",
        archivos_impresion.descargar,
        name="archivo_impresion_descargar",
    ),
    path(
        "<int:producto_id>/archivos-impresion/<int:archivo_id>/predeterminar/",
        archivos_impresion.predeterminar,
        name="archivo_impresion_predeterminar",
    ),
    path(
        "<int:producto_id>/archivos-impresion/<int:archivo_id>/activo/",
        archivos_impresion.cambiar_activo,
        name="archivo_impresion_activo",
    ),
    path(
        "<int:producto_id>/archivos-impresion/<int:archivo_id>/reemplazar/",
        archivos_impresion.reemplazar,
        name="archivo_impresion_reemplazar",
    ),
    path(
        "<int:producto_id>/archivos-impresion/<int:archivo_id>/eliminar/",
        archivos_impresion.eliminar,
        name="archivo_impresion_eliminar",
    ),
    path(
        "<int:producto_id>/imagenes/",
        imagenes_views.imagenes_producto,
        name="imagenes",
    ),
    path(
        "<int:producto_id>/imagenes/subir/",
        imagenes_views.subir_imagen,
        name="imagen_subir",
    ),
    path(
        "<int:producto_id>/imagenes/reemplazar/<int:orden>/",
        imagenes_views.reemplazar_imagen,
        name="imagen_reemplazar",
    ),
    path(
        "<int:producto_id>/imagenes/<int:imagen_id>/principal/",
        imagenes_views.hacer_principal,
        name="imagen_principal",
    ),
    path(
        "<int:producto_id>/imagenes/<int:imagen_id>/eliminar/",
        imagenes_views.eliminar_imagen,
        name="imagen_eliminar",
    ),
    path(
        "<int:producto_id>/activo/",
        views.cambiar_activo,
        name="cambiar_activo",
    ),
    path(
        "<int:producto_id>/armar/",
        views.armar_producto,
        name="armar",
    ),
]
