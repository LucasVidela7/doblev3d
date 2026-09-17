import re

from django.urls import reverse


DASHBOARD_REFINEMENTS_STYLE = r"""
<style id="dv-dashboard-refinements-style">
.dv-panel-title-row{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:12px;
    margin-bottom:17px;
}
.dv-panel-title-row .panel-subtitulo{
    margin-bottom:0!important;
}
.dv-panel-ver-todo{
    flex:0 0 auto;
    display:inline-flex;
    align-items:center;
    min-height:28px;
    padding:0 2px;
    color:#4f555e;
    text-decoration:none;
    font-size:9px;
    font-weight:900;
    letter-spacing:.15px;
    white-space:nowrap;
}
.dv-panel-ver-todo:hover{
    color:#24272b;
    text-decoration:underline;
    text-underline-offset:3px;
}
@media(max-width:420px){
    .dv-panel-title-row{gap:8px}
    .dv-panel-ver-todo{font-size:8px}
}
</style>
"""


_ESTADO_HEADER_RE = re.compile(
    r'(<h2\s+class="seccion-titulo">Estado del taller</h2>)'
    r'\s*<a\b[^>]*class="ver-todo"[^>]*>.*?</a>',
    re.IGNORECASE | re.DOTALL,
)

_NECESIDAD_RE = re.compile(
    r'<h3\s+class="panel-titulo">Necesidad de impresión</h3>'
    r'\s*<div\s+class="panel-subtitulo">'
    r'Productos con más unidades pendientes'
    r'</div>',
    re.IGNORECASE,
)

_ENTREGA_EDIT_RE = re.compile(
    r'href="(?P<href>[^"]*/pedidos/(?P<id>\d+)/editar/)"'
    r'(?P<attrs>\s+class="entrega-link entrega-link-principal"[^>]*)>'
    r'Ver pedido</a>',
    re.IGNORECASE,
)


class DashboardRefinementsMiddleware:
    """Ajustes de navegación puntuales del dashboard sin tocar su lógica."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""

        if (
            view_name != "dashboard:inicio"
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if (
            "dv-dashboard-refinements-style" not in html
            and "</head>" in html
        ):
            html = html.replace(
                "</head>",
                DASHBOARD_REFINEMENTS_STYLE + "\n</head>",
                1,
            )

        # El título de sección vuelve a ser informativo; cada panel expone
        # su propio acceso contextual.
        html = _ESTADO_HEADER_RE.sub(
            r'\1\n        <div class="seccion-ayuda">Información operativa actual</div>',
            html,
            count=1,
        )

        url_impresiones = reverse("pedidos:impresiones_productos")
        cabecera_necesidad = (
            '<div class="dv-panel-title-row">'
            '<div>'
            '<h3 class="panel-titulo">Necesidad de impresión</h3>'
            '<div class="panel-subtitulo">Productos con más unidades pendientes</div>'
            '</div>'
            f'<a href="{url_impresiones}" class="dv-panel-ver-todo" '
            'aria-label="Ver todas las impresiones por producto">'
            'VER TODO →</a>'
            '</div>'
        )
        html = _NECESIDAD_RE.sub(
            cabecera_necesidad,
            html,
            count=1,
        )

        # En próximas entregas, "Ver pedido" abre una ficha de consulta.
        # Editar queda como una acción explícita dentro de esa ficha.
        def reemplazar_detalle(match):
            pedido_id = int(match.group("id"))
            url_detalle = reverse(
                "pedidos:detalle",
                kwargs={"pedido_id": pedido_id},
            )
            return (
                f'href="{url_detalle}"{match.group("attrs")}>'
                'Ver pedido</a>'
            )

        html = _ENTREGA_EDIT_RE.sub(reemplazar_detalle, html)

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
