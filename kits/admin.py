from django.contrib import admin

from .models import Kit, KitComponente


class KitComponenteInline(admin.TabularInline):
    model = KitComponente
    extra = 1
    autocomplete_fields = ["producto"]


@admin.register(Kit)
class KitAdmin(admin.ModelAdmin):
    list_display = [
        "codigo",
        "nombre",
        "modalidad",
        "tipo_producto",
        "cantidad_productos",
        "max_repeticiones_producto",
        "precio",
        "activo",
    ]
    list_filter = [
        "modalidad",
        "activo",
        "tipo_producto",
    ]
    search_fields = [
        "nombre",
    ]
    inlines = [
        KitComponenteInline,
    ]
