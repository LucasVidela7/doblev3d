"""Ajustes visuales finales para Nuevo/Editar Pedido.

Esta capa se aplica después de PedidoFormUIMiddleware en la respuesta HTML y
corrige exclusivamente composición, proporciones y responsive del editor de
precio de kits.
"""


PEDIDO_FORM_LOOKFEEL_STYLE = r"""
<style id="dv-pedido-form-lookfeel">
/* El bloque de precio debe ocupar toda la fila también dentro de la grilla
   histórica de Editar Pedido. */
body.dv-pedido-form-page .dv-kit-price-box{
    grid-column:1 / -1!important;
    width:100%!important;
    min-width:0!important;
    margin-top:4px!important;
    padding:14px!important;
    border-color:#d4e4d9!important;
    border-radius:14px!important;
    background:#f7fbf8!important;
}

body.dv-pedido-form-page .dv-kit-price-head{
    margin-bottom:11px!important;
}

body.dv-pedido-form-page .dv-kit-price-title{
    font-size:9px!important;
    line-height:1.2!important;
    letter-spacing:.35px!important;
}

body.dv-pedido-form-page .dv-kit-price-help{
    max-width:620px;
    margin-top:3px!important;
    font-size:9px!important;
    line-height:1.35!important;
}

body.dv-pedido-form-page .dv-kit-price-state{
    min-height:24px;
    display:inline-flex;
    align-items:center;
    padding:0 9px!important;
    font-size:8px!important;
}

/* En escritorio el editor queda compacto: precio + total + acción.
   Evitamos que TOTAL absorba todo el ancho disponible. */
body.dv-pedido-form-page .dv-kit-price-grid{
    display:grid!important;
    grid-template-columns:minmax(185px,230px) minmax(190px,240px) minmax(150px,175px)!important;
    justify-content:start!important;
    align-items:end!important;
    gap:10px!important;
    width:100%!important;
}

/* Los labels inyectados no estaban dentro de .campo y heredaban estilos
   distintos entre Nuevo y Editar. Los unificamos acá. */
body.dv-pedido-form-page .dv-kit-price-grid label{
    display:block!important;
    margin:0 0 6px!important;
    color:#73777f!important;
    font-size:9px!important;
    font-weight:900!important;
    line-height:1.15!important;
    letter-spacing:.28px!important;
}

body.dv-pedido-form-page .dv-kit-price-grid input[type="number"]{
    min-height:50px!important;
    height:50px!important;
    padding:9px 12px!important;
    border-radius:12px!important;
    font-size:14px!important;
    font-weight:500!important;
}

body.dv-pedido-form-page .dv-kit-price-total{
    min-height:50px!important;
    height:50px!important;
    padding:0 12px!important;
    border-color:#dce3df!important;
    border-radius:12px!important;
    font-size:10px!important;
    line-height:1.25!important;
    white-space:nowrap;
}

body.dv-pedido-form-page .dv-kit-auto-btn{
    min-height:50px!important;
    height:50px!important;
    padding:0 12px!important;
    border-radius:12px!important;
    font-size:8px!important;
    line-height:1.2!important;
}

body.dv-pedido-form-page .dv-kit-reference{
    display:inline-flex!important;
    max-width:760px!important;
    margin-top:9px!important;
    padding:7px 10px!important;
    border-radius:9px!important;
    background:#edf4ef!important;
    font-size:8px!important;
    line-height:1.35!important;
}

/* Tablet horizontal / vertical: dos columnas y acción debajo para no
   comprimir el texto ni volver a estirar el total. */
@media (min-width:651px) and (max-width:900px){
    body.dv-pedido-form-page .dv-kit-price-grid{
        grid-template-columns:minmax(180px,230px) minmax(190px,250px)!important;
    }

    body.dv-pedido-form-page .dv-kit-auto-btn{
        grid-column:1 / -1!important;
        width:max-content!important;
        min-width:170px!important;
    }
}

/* Móvil: una sola columna, jerarquía clara y controles cómodos. */
@media (max-width:650px){
    body.dv-pedido-form-page .dv-kit-price-box{
        padding:12px!important;
        margin-top:2px!important;
    }

    body.dv-pedido-form-page .dv-kit-price-head{
        gap:7px!important;
        margin-bottom:10px!important;
    }

    body.dv-pedido-form-page .dv-kit-price-grid{
        grid-template-columns:1fr!important;
        gap:9px!important;
    }

    body.dv-pedido-form-page .dv-kit-price-total{
        width:100%!important;
        white-space:normal!important;
    }

    body.dv-pedido-form-page .dv-kit-auto-btn{
        width:100%!important;
    }

    body.dv-pedido-form-page .dv-kit-reference{
        display:flex!important;
        width:100%!important;
        max-width:none!important;
    }
}
</style>
"""


class PedidoFormLookFeelMiddleware:
    """Inyecta los ajustes visuales finales sólo en Nuevo/Editar Pedido."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        resolver = getattr(request, "resolver_match", None)
        view_name = resolver.view_name if resolver else ""
        if view_name not in {"pedidos:nuevo", "pedidos:editar", "pedidos:presupuesto_editar"}:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if (
            "dv-pedido-form-lookfeel" not in html
            and "</head>" in html
        ):
            html = html.replace(
                "</head>",
                PEDIDO_FORM_LOOKFEEL_STYLE + "\n</head>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
