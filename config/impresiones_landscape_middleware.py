"""Corrección específica para Impresiones por producto en tablet horizontal.

En tablets apaisadas el viewport puede superar el breakpoint clásico de tablet
y la pantalla vuelve a mostrarse como una tabla de escritorio. Este middleware
mantiene el modo tarjeta cuando existe un puntero táctil, sin alterar escritorio.
"""


LANDSCAPE_STYLE = r"""
<style id="dv-impresiones-landscape-fix">
@media
    (orientation: landscape) and (min-width: 1101px) and (any-pointer: coarse),
    (orientation: landscape) and (min-width: 1101px) and (hover: none) {

    body {
        padding: 0 0 98px !important;
    }

    .contenedor {
        width: 100% !important;
        max-width: none !important;
        padding: 14px 16px 28px !important;
    }

    .tabla-contenedor {
        overflow: visible !important;
        background: transparent !important;
        border-radius: 0 !important;
        box-shadow: none !important;
    }

    .tabla-contenedor table {
        display: block !important;
        width: 100% !important;
        min-width: 0 !important;
        table-layout: auto !important;
    }

    .tabla-contenedor thead {
        display: none !important;
    }

    .tabla-contenedor tbody {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        gap: 14px !important;
        width: 100% !important;
    }

    .tabla-contenedor tbody tr {
        display: grid !important;
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 0 !important;
        width: 100% !important;
        min-width: 0 !important;
        overflow: hidden !important;
        border: 1px solid #e2e5e9 !important;
        border-radius: 16px !important;
        background: #fff !important;
        box-shadow: 0 3px 14px rgba(20, 25, 35, .06) !important;
    }

    .tabla-contenedor tbody td,
    .tabla-contenedor tbody td.numero,
    .tabla-contenedor tbody td.columna-prioridad {
        display: flex !important;
        width: auto !important;
        max-width: none !important;
        min-width: 0 !important;
        min-height: 58px !important;
        padding: 9px 11px !important;
        border: 0 !important;
        border-right: 1px solid #eef0f2 !important;
        border-bottom: 1px solid #eef0f2 !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: center !important;
        text-align: left !important;
    }

    .tabla-contenedor tbody td::before {
        content: attr(data-label);
        display: block !important;
        margin-bottom: 5px !important;
        color: #858a91 !important;
        font-size: 7px !important;
        font-weight: 900 !important;
        line-height: 1.15 !important;
        letter-spacing: .25px !important;
    }

    .tabla-contenedor tbody td.producto {
        grid-column: 1 / -1 !important;
        width: 100% !important;
        min-height: auto !important;
        padding: 12px !important;
        border-right: 0 !important;
        background: #fafbfc !important;
        font-size: 13px !important;
        font-weight: 900 !important;
    }

    .tabla-contenedor tbody td.producto::before {
        display: none !important;
    }

    .tabla-contenedor .codigo {
        display: block !important;
        margin: 0 0 3px !important;
        font-size: 8px !important;
        font-weight: 900 !important;
    }

    .tabla-contenedor tbody td.numero,
    .tabla-contenedor .cantidad,
    .tabla-contenedor .imprimir,
    .tabla-contenedor .personalizado,
    .tabla-contenedor .produccion-activa,
    .tabla-contenedor .produccion-cero,
    .tabla-contenedor .falta-iniciar {
        font-size: 15px !important;
        line-height: 1.1 !important;
    }

    .tabla-contenedor tbody td.columna-prioridad {
        justify-content: center !important;
    }

    .tabla-contenedor .prioridad {
        min-width: 0 !important;
        padding: 5px 8px !important;
        font-size: 8px !important;
    }

    .tabla-contenedor .dv-planificar-celda {
        grid-column: 1 / -1 !important;
        width: 100% !important;
        min-width: 0 !important;
        min-height: auto !important;
        padding: 10px 11px 11px !important;
        border: 0 !important;
        background: #fbfcfd !important;
        align-items: stretch !important;
    }

    .tabla-contenedor .dv-planificar-celda::before {
        content: "PLANIFICACIÓN" !important;
        margin-bottom: 7px !important;
    }

    .dv-planificar-celda > *,
    .dv-plan-resumen,
    .dv-plan-details,
    .dv-personalizados,
    .dv-personalizado,
    .dv-plan-form {
        width: 100% !important;
        max-width: none !important;
        min-width: 0 !important;
    }

    .dv-plan-details > summary {
        min-height: 40px !important;
        display: flex !important;
        align-items: center !important;
        padding: 8px 10px !important;
        font-size: 8px !important;
    }

    .dv-plan-form {
        display: grid !important;
        grid-template-columns:
            minmax(96px, .55fr)
            minmax(190px, 1.25fr)
            minmax(210px, 1fr) !important;
        align-items: end !important;
        gap: 8px !important;
        padding: 10px !important;
    }

    .dv-plan-fecha,
    .dv-plan-duracion {
        grid-column: auto !important;
    }

    .dv-plan-duracion {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        gap: 8px !important;
        min-width: 0 !important;
    }

    .dv-plan-campo {
        min-width: 0 !important;
    }

    .dv-plan-campo input {
        width: 100% !important;
        min-width: 0 !important;
        min-height: 40px !important;
        font-size: 11px !important;
    }

    .dv-plan-campo label {
        min-height: 18px !important;
        display: flex !important;
        align-items: flex-end !important;
        line-height: 1.15 !important;
    }

    .dv-plan-tiempo,
    .dv-plan-enviar {
        grid-column: 1 / -1 !important;
    }

    .dv-plan-enviar {
        min-height: 40px !important;
    }
}
</style>
"""


class ImpresionesLandscapeMiddleware:
    """Mantiene la vista operativa en tarjetas en tablets horizontales."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""

        if (
            view_name != "pedidos:impresiones_productos"
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
            or response.status_code != 200
        ):
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "dv-impresiones-landscape-fix" not in html and "</head>" in html:
            html = html.replace(
                "</head>",
                LANDSCAPE_STYLE + "\n</head>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
