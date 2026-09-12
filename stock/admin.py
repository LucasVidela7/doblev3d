from django.contrib import admin

from .models import MovimientoStock


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):

    list_display = (
        "fecha",
        "producto",
        "tipo",
        "mostrar_cantidad",
        "referencia",
    )

    list_filter = (
        "tipo",
        "fecha",
    )

    search_fields = (
        "producto__nombre",
        "referencia",
    )

    autocomplete_fields = (
        "producto",
    )

    readonly_fields = (
        "fecha",
    )

    @admin.display(description="MOVIMIENTO")
    def mostrar_cantidad(self, obj):

        cantidad = obj.cantidad_con_signo

        if cantidad > 0:
            return f"+{cantidad}"

        return str(cantidad)