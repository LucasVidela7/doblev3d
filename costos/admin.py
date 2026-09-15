from django.contrib import admin

from .models import ConfiguracionCostos, TramoCostoFilamento


class TramoCostoFilamentoInline(admin.TabularInline):
    model = TramoCostoFilamento
    extra = 2
    fields = (
        "desde_gramos",
        "coste_plastico_kg",
        "activo",
    )
    ordering = ("desde_gramos",)


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

    inlines = [TramoCostoFilamentoInline]

    fieldsets = (
        (
            "Configuración general",
            {
                "fields": (
                    "nombre",
                    "fecha_desde",
                    "activa",
                )
            },
        ),
        (
            "Costos estándar del producto",
            {
                "description": (
                    "El coste plástico por kg de esta sección sigue siendo el "
                    "valor conservador usado para productos individuales y "
                    "precio de lista. Los tramos de volumen de abajo sólo se "
                    "aplican en la calculadora de cantidades y en kits."
                ),
                "fields": (
                    "coste_plastico_kg",
                    "tasa_fallos",
                    "coste_luz_hora",
                    "coste_amortizacion_hora",
                ),
            },
        ),
    )
