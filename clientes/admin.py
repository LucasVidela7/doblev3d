from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):

    list_display = (
        "mostrar_codigo",
        "nombre",
        "telefono",
        "email",
        "activo",
    )

    search_fields = (
        "nombre",
        "telefono",
        "email",
    )

    list_filter = (
        "activo",
    )

    @admin.display(
        description="ID CLIENTE",
        ordering="id"
    )
    def mostrar_codigo(self, obj):
        return obj.codigo