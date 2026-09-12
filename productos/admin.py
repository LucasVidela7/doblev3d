from django.contrib import admin

from .models import Producto, TipoProducto


@admin.register(TipoProducto)
class TipoProductoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "activo",
    )

    search_fields = (
        "nombre",
    )

    list_filter = (
        "activo",
    )


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = (
        "mostrar_codigo",
        "nombre",
        "categoria",
        "tipo",
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

    search_fields = (
        "nombre",
    )

    list_filter = (
        "categoria",
        "requiere_impresion",
        "personalizable",
        "activo",
    )

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

    @admin.display(
        description="ID PRODUCTO",
        ordering="id"
    )
    def mostrar_codigo(self, obj):
        return obj.codigo
