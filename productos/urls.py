from django.urls import path

from . import views
from . import imagenes_views
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
