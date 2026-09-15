"""Ajustes responsive puntuales para pantallas operativas.

Se mantiene separado de la lógica de negocio para poder corregir templates
históricos sin duplicar sus formularios dinámicos.
"""


ORDENES_RESPONSIVE_STYLE = r"""
<style id="dv-ordenes-responsive-fix">
/*
 * Los textos auxiliares debajo de Producto / Producto base no deben cambiar
 * la alineación vertical de TIPO, CANTIDAD, COLOR o PRECIO.
 */
.item-grid,
.item > .grid,
.personalizado-grid,
.personal-box.grid {
    align-items: start !important;
}

.item-grid > *,
.item > .grid > *,
.personalizado-grid > *,
.personal-box.grid > * {
    align-self: start !important;
    min-width: 0;
}

.dv-sin-piezas-aviso {
    margin-top: 5px !important;
    min-height: 12px;
    line-height: 1.3 !important;
}

/* Nuevo pedido: conservar una fila limpia también en tablet. */
@media (min-width: 721px) and (max-width: 1050px) {
    .item-grid {
        grid-template-columns: 150px minmax(0, 1fr) 105px !important;
        gap: 10px !important;
    }

    .personalizado-grid {
        grid-template-columns:
            minmax(240px, 1.55fr)
            minmax(120px, .65fr)
            minmax(150px, .8fr) !important;
        gap: 10px !important;
    }
}

/* Móvil: todos los campos se apilan sin dependencias de altura entre ellos. */
@media (max-width: 720px) {
    .item-grid,
    .item > .grid,
    .personalizado-grid,
    .personal-box.grid {
        grid-template-columns: 1fr !important;
    }

    .personal-box.grid .full,
    .item > .grid .full {
        grid-column: 1 !important;
    }
}
</style>
"""


IMPRESIONES_RESPONSIVE_STYLE = r"""
<style id="dv-impresiones-responsive-fix">
/* Encabezado compacto. Evita que flex-basis se convierta en altura en tablet. */
body {
    padding-top: 0 !important;
}

.contenedor {
    padding-top: 16px !important;
}

.encabezado {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) auto !important;
    align-items: center !important;
    gap: 12px !important;
    margin-bottom: 16px !important;
}

.encabezado > .encabezado-marca {
    flex: none !important;
    flex-basis: auto !important;
    min-width: 0 !important;
    min-height: 52px !important;
}

.encabezado > .acciones-encabezado {
    width: auto !important;
    display: flex !important;
    flex-wrap: nowrap !important;
    justify-content: flex-end !important;
}

/* Escritorio: reducir ancho sin perder información. */
.tabla-contenedor table {
    table-layout: auto;
}

.tabla-contenedor th,
.tabla-contenedor td {
    padding: 11px 10px !important;
}

.tabla-contenedor .numero {
    width: 92px !important;
}

.tabla-contenedor .columna-prioridad {
    width: 126px !important;
}

.dv-planificar-celda {
    min-width: 250px !important;
    width: 280px;
}

/* Tablet: cada producto pasa a ser una tarjeta operativa. */
@media (max-width: 1100px) {
    body {
        padding: 0 0 98px !important;
    }

    .contenedor {
        width: 100% !important;
        padding: 14px 14px 28px !important;
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
    }

    .tabla-contenedor thead {
        display: none !important;
    }

    .tabla-contenedor tbody {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        width: 100%;
    }

    .tabla-contenedor tbody tr {
        display: grid !important;
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 0;
        width: 100%;
        min-width: 0;
        overflow: hidden;
        border: 1px solid #e2e5e9;
        border-radius: 16px;
        background: #fff !important;
        box-shadow: 0 3px 14px rgba(20, 25, 35, .06);
    }

    /*
     * IMPORTANTE: en modo tarjeta anulamos los width:92px/126px usados por
     * la tabla de escritorio. Si quedan activos, Grid usa esas medidas para
     * calcular las columnas y la tarjeta queda visualmente deformada.
     */
    .tabla-contenedor tbody td,
    .tabla-contenedor tbody td.numero,
    .tabla-contenedor tbody td.columna-prioridad {
        display: flex !important;
        width: auto !important;
        max-width: none !important;
        min-width: 0 !important;
        min-height: 60px;
        padding: 9px 11px !important;
        border: 0 !important;
        border-right: 1px solid #eef0f2 !important;
        border-bottom: 1px solid #eef0f2 !important;
        flex-direction: column;
        align-items: flex-start !important;
        justify-content: center;
        text-align: left !important;
    }

    .tabla-contenedor tbody td::before {
        content: attr(data-label);
        display: block;
        margin-bottom: 5px;
        color: #858a91;
        font-size: 7px;
        font-weight: 900;
        line-height: 1.15;
        letter-spacing: .25px;
    }

    .tabla-contenedor tbody td.producto {
        grid-column: 1 / -1;
        width: 100% !important;
        min-height: auto;
        padding: 12px !important;
        border-right: 0 !important;
        background: #fafbfc;
        font-size: 13px;
        font-weight: 900;
    }

    .tabla-contenedor tbody td.producto::before {
        display: none;
    }

    .tabla-contenedor .codigo {
        display: block;
        margin: 0 0 3px !important;
        font-size: 8px;
        font-weight: 900;
    }

    .tabla-contenedor tbody td.numero,
    .tabla-contenedor .cantidad,
    .tabla-contenedor .imprimir,
    .tabla-contenedor .personalizado,
    .tabla-contenedor .produccion-activa,
    .tabla-contenedor .produccion-cero,
    .tabla-contenedor .falta-iniciar {
        font-size: 15px !important;
        line-height: 1.1;
    }

    .tabla-contenedor .personalizado-cero {
        display: none !important;
    }

    .tabla-contenedor tbody td.columna-prioridad {
        justify-content: center;
    }

    .tabla-contenedor .prioridad {
        min-width: 0 !important;
        padding: 5px 8px !important;
        font-size: 8px !important;
    }

    .tabla-contenedor .detalle-impresora {
        font-size: 7px !important;
    }

    .dv-planificar-celda {
        grid-column: 1 / -1;
        width: 100% !important;
        min-width: 0 !important;
        min-height: auto !important;
        padding: 10px 11px 11px !important;
        border: 0 !important;
        background: #fbfcfd;
    }

    .dv-planificar-celda::before {
        content: "PLANIFICACIÓN" !important;
        margin-bottom: 7px !important;
    }

    .dv-plan-resumen {
        width: 100%;
        margin-bottom: 4px !important;
    }

    .dv-plan-details {
        width: 100%;
        margin-top: 6px !important;
    }

    .dv-plan-details > summary {
        min-height: 40px;
        display: flex;
        align-items: center;
        padding: 8px 10px !important;
        font-size: 8px !important;
    }

    .dv-plan-form {
        width: 100%;
        grid-template-columns: 82px minmax(0, 1fr) !important;
    }

    .dv-plan-campo input {
        font-size: 12px !important;
    }
}

/* Tablet vertical: una tarjeta por fila y métricas realmente simétricas. */
@media (max-width: 900px) {
    .tabla-contenedor tbody {
        grid-template-columns: 1fr !important;
    }

    .tabla-contenedor tbody tr {
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }

    .tabla-contenedor tbody td:nth-child(3n + 1) {
        border-right-color: #eef0f2 !important;
    }
}

@media (max-width: 650px) {
    .contenedor {
        padding: 12px 10px 25px !important;
    }

    .encabezado {
        grid-template-columns: 1fr !important;
        align-items: stretch !important;
        gap: 10px !important;
    }

    .encabezado > .encabezado-marca {
        min-height: 48px !important;
    }

    .encabezado > .acciones-encabezado {
        width: 100% !important;
    }

    .encabezado > .acciones-encabezado > * {
        flex: 1 1 0 !important;
    }

    .tabla-contenedor tbody tr {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }

    .tabla-contenedor tbody td {
        min-height: 58px;
    }

    .dv-plan-form {
        grid-template-columns: 1fr !important;
    }

    .dv-plan-fecha,
    .dv-plan-duracion {
        grid-column: 1 !important;
    }

    .dv-plan-duracion {
        grid-template-columns: 1fr 1fr !important;
    }
}
</style>
"""


IMPRESIONES_RESPONSIVE_SCRIPT = r"""
<script id="dv-impresiones-responsive-script">
(function(){
    function normalizar(texto){
        return (texto || '').replace(/\s+/g, ' ').trim();
    }

    function preparar(){
        var tabla = document.querySelector('.tabla-contenedor table');
        if (!tabla || tabla.dataset.dvResponsive === '1') return;

        var encabezados = Array.from(
            tabla.querySelectorAll('thead th')
        ).map(function(th){
            return normalizar(th.textContent).toUpperCase();
        });

        tabla.querySelectorAll('tbody tr').forEach(function(fila){
            Array.from(fila.children).forEach(function(celda, indice){
                if (celda.tagName !== 'TD') return;
                var etiqueta = encabezados[indice] || '';
                if (celda.classList.contains('dv-planificar-celda')) {
                    etiqueta = 'PLANIFICACIÓN';
                }
                celda.dataset.label = etiqueta;
            });
        });

        tabla.dataset.dvResponsive = '1';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', preparar);
    } else {
        preparar();
    }
})();
</script>
"""


class ResponsiveFixesMiddleware:
    """Corrige composición responsive sin modificar lógica de negocio."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""

        if (
            getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        if view_name not in {
            "pedidos:nuevo",
            "pedidos:editar",
            "pedidos:impresiones_productos",
        }:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if view_name in {"pedidos:nuevo", "pedidos:editar"}:
            if "dv-ordenes-responsive-fix" not in html and "</head>" in html:
                html = html.replace(
                    "</head>",
                    ORDENES_RESPONSIVE_STYLE + "\n</head>",
                    1,
                )

        if view_name == "pedidos:impresiones_productos":
            if "dv-impresiones-responsive-fix" not in html and "</head>" in html:
                html = html.replace(
                    "</head>",
                    IMPRESIONES_RESPONSIVE_STYLE + "\n</head>",
                    1,
                )
            if "dv-impresiones-responsive-script" not in html and "</body>" in html:
                html = html.replace(
                    "</body>",
                    IMPRESIONES_RESPONSIVE_SCRIPT + "\n</body>",
                    1,
                )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
