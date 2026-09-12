from django.contrib import admin

from .models import (
    Pedido,
    DetallePedido,
    DetalleKitProducto,
)


class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 1

    fields = (
        "tipo_item",
        "producto",
        "kit",
        "cantidad",
        "precio_unitario",
        "estado",
        "personalizado",
    )

    autocomplete_fields = (
        "producto",
        "kit",
    )


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):

    list_display = (
        "mostrar_codigo",
        "fecha",
        "cliente",
        "estado",
        "fecha_entrega",
        "mostrar_total",
    )

    search_fields = (
        "cliente__nombre",
        "cliente__telefono",
    )

    list_filter = (
        "estado",
        "fecha",
        "fecha_entrega",
    )

    autocomplete_fields = (
        "cliente",
    )

    inlines = (
        DetallePedidoInline,
    )

    @admin.display(
        description="ID PEDIDO",
        ordering="id"
    )
    def mostrar_codigo(self, obj):
        return obj.codigo

    @admin.display(description="TOTAL")
    def mostrar_total(self, obj):
        return f"${obj.total:,.0f}"


class DetalleKitProductoInline(admin.TabularInline):
    model = DetalleKitProducto
    extra = 1

    autocomplete_fields = (
        "producto",
    )


@admin.register(DetallePedido)
class DetallePedidoAdmin(admin.ModelAdmin):

    list_display = (
        "pedido",
        "tipo_item",
        "mostrar_item",
        "cantidad",
        "precio_unitario",
        "mostrar_subtotal",
        "estado",
    )

    list_filter = (
        "tipo_item",
        "estado",
        "personalizado",
    )

    search_fields = (
        "pedido__cliente__nombre",
        "producto__nombre",
        "kit__nombre",
    )

    autocomplete_fields = (
        "producto",
        "kit",
    )

    inlines = (
        DetalleKitProductoInline,
    )

    @admin.display(description="ITEM")
    def mostrar_item(self, obj):

        if obj.tipo_item == "PRODUCTO" and obj.producto:
            return obj.producto.nombre

        if obj.tipo_item == "KIT" and obj.kit:
            return obj.kit.nombre

        return "-"

    @admin.display(description="SUBTOTAL")
    def mostrar_subtotal(self, obj):
        return f"${obj.subtotal:,.0f}"