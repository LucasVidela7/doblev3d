from django.contrib import admin

from .models import ConfiguracionCostos


@admin.register(ConfiguracionCostos)
class ConfiguracionCostosAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "coste_plastico_kg",
        "tasa_fallos",
        "coste_luz_hora",
        "coste_amortizacion_hora",
        "fecha_desde",
        "activa",
    )

    list_filter = (
        "activa",
        "fecha_desde",
    )

    ordering = (
        "-fecha_desde",
    )