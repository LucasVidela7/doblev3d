import json

from django.contrib import admin
from django.utils.html import format_html

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "usuario_nombre",
        "accion",
        "app_label",
        "modelo",
        "objeto_representacion",
        "ip",
    )
    list_filter = (
        "accion",
        "app_label",
        "modelo",
        "usuario",
        "fecha",
    )
    search_fields = (
        "usuario_nombre",
        "objeto_id",
        "objeto_representacion",
        "ruta",
    )
    date_hierarchy = "fecha"
    ordering = ("-fecha", "-id")
    readonly_fields = (
        "fecha",
        "usuario",
        "usuario_nombre",
        "accion",
        "app_label",
        "modelo",
        "objeto_id",
        "objeto_representacion",
        "cambios_formateados",
        "ruta",
        "metodo",
        "ip",
    )
    fields = readonly_fields

    @admin.display(description="Cambios")
    def cambios_formateados(self, obj):
        if not obj.cambios:
            return "Sin cambios de campos"
        contenido = json.dumps(obj.cambios, ensure_ascii=False, indent=2, default=str)
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", contenido)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff
