from django.contrib import admin

from .models import Kit


@admin.register(Kit)
class KitAdmin(admin.ModelAdmin):

    list_display = (
        "mostrar_codigo",
        "nombre",
        "tipo_producto",
        "cantidad_productos",
        "precio",
        "activo",
    )

    search_fields = (
        "nombre",
    )

    list_filter = (
        "tipo_producto",
        "activo",
    )

    @admin.display(
        description="ID KIT",
        ordering="id"
    )
    def mostrar_codigo(self, obj):
        return obj.codigo