from django.contrib import admin

from .models import (
    ConfiguracionCatalogo,
    Insumo,
    Producto,
    ProductoComponente,
    TipoProducto,
)


@admin.register(ConfiguracionCatalogo)
class ConfiguracionCatalogoAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Instagram",
            {
                "fields": (
                    "mostrar_instagram",
                    "instagram_usuario",
                ),
            },
        ),
        (
            "WhatsApp",
            {
                "fields": (
                    "mostrar_whatsapp",
                    "whatsapp_numero",
                    "whatsapp_mensaje",
                    "whatsapp_mensaje_respuesta_solicitud",
                    "whatsapp_mensaje_post_solicitud",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return not ConfiguracionCatalogo.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Insumo)
class InsumoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "nombre",
        "tipo_uso",
        "unidad_medida",
        "precio_compra",
        "cantidad_compra",
        "stock",
        "activo",
    )
    search_fields = ("nombre", "proveedor")
    list_filter = ("tipo_uso", "unidad_medida", "activo")


@admin.register(TipoProducto)
class TipoProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)


class ProductoComponenteInline(admin.TabularInline):
    model = ProductoComponente
    fk_name = "producto"
    extra = 1
    autocomplete_fields = ("componente",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = (
        "mostrar_codigo",
        "nombre",
        "categoria",
        "tipo",
        "tipo_fabricacion",
        "solo_produccion",
        "horas",
        "minutos",
        "peso_gramos",
        "margen_ganancia",
        "requiere_impresion",
        "personalizable",
        "stock",
        "mostrar_costo",
        "mostrar_seguro",
        "mostrar_ganancia",
        "mostrar_subtotal",
    )
    search_fields = ("nombre",)
    list_filter = (
        "categoria",
        "tipo_fabricacion",
        "solo_produccion",
        "requiere_impresion",
        "personalizable",
        "activo",
    )
    inlines = (ProductoComponenteInline,)

    @admin.display(description="COSTO")
    def mostrar_costo(self, obj):
        return f"${obj.costo:,.0f}"

    @admin.display(description="SEGURO")
    def mostrar_seguro(self, obj):
        return f"${obj.seguro:,.0f}"

    @admin.display(description="GANANCIA")
    def mostrar_ganancia(self, obj):
        return f"${obj.ganancia:,.0f}"

    @admin.display(description="SUBTOTAL")
    def mostrar_subtotal(self, obj):
        return f"${obj.subtotal:,.0f}"

    @admin.display(description="ID PRODUCTO", ordering="id")
    def mostrar_codigo(self, obj):
        return obj.codigo
