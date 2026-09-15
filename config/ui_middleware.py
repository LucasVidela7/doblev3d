from html import escape

from django.middleware.csrf import get_token
from django.urls import reverse


NAV_STYLE = r"""
<style id="dv-nav-actions-style">
.dv-nav-action{
    min-height:50px!important;
    height:auto!important;
    padding:0 18px!important;
    border-radius:14px!important;
    font-family:Arial,sans-serif!important;
    font-size:11px!important;
    font-weight:900!important;
    line-height:1!important;
    display:inline-flex!important;
    align-items:center!important;
    justify-content:center!important;
    text-decoration:none!important;
    cursor:pointer!important;
    box-sizing:border-box!important;
    white-space:nowrap!important;
    transition:background .15s ease,border-color .15s ease,color .15s ease!important;
}
.dv-nav-back{
    border:1px solid #e5e7eb!important;
    background:#fff!important;
    color:#24272b!important;
    box-shadow:none!important;
}
.dv-nav-home{
    border:1px solid #24272b!important;
    background:#24272b!important;
    color:#fff!important;
    box-shadow:none!important;
}
@media(hover:hover){
    .dv-nav-back:hover{background:#f0f1f3!important}
    .dv-nav-home:hover{background:#16191d!important;border-color:#16191d!important}
}
@media(max-width:720px){
    .dv-nav-action{min-height:50px!important}
}
</style>
"""

NAV_SCRIPT = r"""
<script id="dv-nav-actions-script">
(function(){
    function normalizar(texto){
        return (texto || '').replace(/\s+/g, ' ').trim().toUpperCase();
    }

    function aplicar(){
        document.querySelectorAll('a, button').forEach(function(el){
            var texto = normalizar(el.textContent);

            if (texto === '← VOLVER' || texto === 'VOLVER') {
                el.classList.add('dv-nav-action', 'dv-nav-back');
            }

            if (texto === 'INICIO') {
                el.classList.add('dv-nav-action', 'dv-nav-home');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', aplicar);
    } else {
        aplicar();
    }
})();
</script>
"""

DASHBOARD_SESSION_STYLE = r"""
<style id="dv-dashboard-session-style">
.dv-dashboard-session{
    display:flex;
    align-items:center;
    justify-content:flex-end;
    gap:10px;
    flex-wrap:wrap;
}
.dv-dashboard-user{
    display:inline-flex;
    align-items:center;
    min-height:38px;
    padding:0 12px;
    border:1px solid #e5e7eb;
    border-radius:12px;
    background:#fff;
    color:#24272b;
    font-family:Arial,sans-serif;
    font-size:11px;
    font-weight:800;
    white-space:nowrap;
}
.dv-dashboard-logout-form{
    margin:0;
}
.dv-dashboard-logout{
    min-height:38px;
    padding:0 13px;
    border:1px solid #d7d9dd;
    border-radius:12px;
    background:#fff;
    color:#5f636b;
    font-family:Arial,sans-serif;
    font-size:10px;
    font-weight:900;
    cursor:pointer;
    white-space:nowrap;
}
@media(hover:hover){
    .dv-dashboard-logout:hover{
        background:#f0f1f3;
        color:#24272b;
    }
}
@media(max-width:720px){
    .dv-dashboard-session{
        width:100%;
        justify-content:flex-end;
        gap:7px;
    }
    .dv-dashboard-user,
    .dv-dashboard-logout{
        min-height:36px;
        padding:0 10px;
        font-size:9px;
    }
}
</style>
"""


def _dashboard_session_html(request):
    usuario = escape(request.user.get_username())
    csrf_token = escape(get_token(request))
    logout_url = escape(reverse("logout"))

    return f"""
<div id="dv-dashboard-session" class="dv-dashboard-session">
    <div class="dv-dashboard-user" title="Usuario conectado">👤 {usuario}</div>
    <form method="post" action="{logout_url}" class="dv-dashboard-logout-form">
        <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
        <button type="submit" class="dv-dashboard-logout">CERRAR SESIÓN</button>
    </form>
</div>
<script id="dv-dashboard-session-script">
(function(){{
    function colocarSesion(){{
        var sesion = document.getElementById('dv-dashboard-session');
        var encabezado = document.querySelector('.encabezado');
        if (!sesion || !encabezado) return;

        var fecha = encabezado.querySelector('.fecha');
        if (fecha){{
            sesion.insertBefore(fecha, sesion.firstChild);
        }}
        encabezado.appendChild(sesion);
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', colocarSesion);
    }} else {{
        colocarSesion();
    }}
}})();
</script>
"""


class NormalizarNavegacionMiddleware:
    """Normaliza navegación e incorpora acciones comunes de la interfaz."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(response, "streaming", False):
            return response

        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "</head>" in html and "dv-nav-actions-style" not in html:
            html = html.replace(
                "</head>",
                NAV_STYLE + "\n</head>",
                1,
            )

        if "</body>" in html and "dv-nav-actions-script" not in html:
            html = html.replace(
                "</body>",
                NAV_SCRIPT + "\n</body>",
                1,
            )

        resolver_match = getattr(request, "resolver_match", None)
        es_dashboard = (
            resolver_match is not None
            and resolver_match.view_name == "dashboard:inicio"
        )

        if (
            es_dashboard
            and request.user.is_authenticated
            and "dv-dashboard-session" not in html
        ):
            if "</head>" in html:
                html = html.replace(
                    "</head>",
                    DASHBOARD_SESSION_STYLE + "\n</head>",
                    1,
                )
            if "</body>" in html:
                html = html.replace(
                    "</body>",
                    _dashboard_session_html(request) + "\n</body>",
                    1,
                )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
