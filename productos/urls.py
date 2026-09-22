from django.urls import path

from . import views
from . import imagenes_views
from . import imagenes_masivas
from . import modificacion_masiva
from .tipos import crear_tipo_producto


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
