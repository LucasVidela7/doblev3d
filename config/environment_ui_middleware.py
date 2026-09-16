import re

from django.conf import settings


QA_HEAD = r"""
<style id="dv-qa-environment-style">
html[data-dv-env="qa"]{
    --dv-qa-accent:#7c3aed;
    --dv-qa-accent-dark:#5b21b6;
    --dv-qa-warning:#f59e0b;
    --dv-qa-surface:#faf7ff;
}

html[data-dv-env="qa"] body{
    background-color:var(--dv-qa-surface)!important;
    box-shadow:
        inset 4px 0 0 var(--dv-qa-accent),
        inset -4px 0 0 var(--dv-qa-accent)!important;
}

html[data-dv-env="qa"] body::after{
    content:"QA";
    position:fixed;
    right:12px;
    bottom:12px;
    z-index:2147483646;
    display:flex;
    align-items:center;
    justify-content:center;
    width:58px;
    height:58px;
    border:2px solid rgba(255,255,255,.92);
    border-radius:18px;
    background:rgba(91,33,182,.9);
    color:#fff;
    box-shadow:0 12px 30px rgba(76,29,149,.28);
    font:900 20px/1 Arial,sans-serif;
    letter-spacing:1px;
    pointer-events:none;
    backdrop-filter:blur(7px);
}

html[data-dv-env="qa"] ::selection{
    background:#ddd6fe;
    color:#2e1065;
}

html[data-dv-env="qa"] input:focus,
html[data-dv-env="qa"] select:focus,
html[data-dv-env="qa"] textarea:focus{
    border-color:var(--dv-qa-accent)!important;
    box-shadow:0 0 0 3px rgba(124,58,237,.14)!important;
    outline:none!important;
}

html[data-dv-env="qa"] a:focus-visible,
html[data-dv-env="qa"] button:focus-visible{
    outline:3px solid rgba(124,58,237,.5)!important;
    outline-offset:2px!important;
}

html[data-dv-env="qa"] .encabezado,
html[data-dv-env="qa"] header{
    border-color:rgba(124,58,237,.28)!important;
}

.dv-qa-banner{
    position:sticky;
    top:0;
    z-index:2147483647;
    min-height:42px;
    display:flex;
    align-items:center;
    justify-content:center;
    gap:10px;
    padding:8px 16px;
    box-sizing:border-box;
    background:linear-gradient(100deg,#5b21b6 0%,#7c3aed 58%,#c2410c 100%);
    color:#fff;
    border-bottom:3px solid #fbbf24;
    box-shadow:0 5px 18px rgba(76,29,149,.24);
    font-family:Arial,sans-serif;
    text-align:center;
}

.dv-qa-banner__pill{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    min-height:24px;
    padding:0 9px;
    border:1px solid rgba(255,255,255,.55);
    border-radius:999px;
    background:rgba(255,255,255,.15);
    font-size:11px;
    font-weight:900;
    letter-spacing:1px;
}

.dv-qa-banner__text{
    font-size:11px;
    font-weight:900;
    letter-spacing:.35px;
}

.dv-qa-banner__hint{
    font-size:10px;
    font-weight:700;
    opacity:.9;
}

@media(max-width:640px){
    .dv-qa-banner{
        min-height:46px;
        gap:7px;
        padding:7px 10px;
        flex-wrap:wrap;
    }
    .dv-qa-banner__text{font-size:10px}
    .dv-qa-banner__hint{display:none}
    html[data-dv-env="qa"] body::after{
        right:8px;
        bottom:8px;
        width:48px;
        height:48px;
        border-radius:15px;
        font-size:17px;
    }
}
</style>
<link id="dv-qa-favicon" rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%237c3aed'/%3E%3Ctext x='32' y='41' text-anchor='middle' font-family='Arial' font-size='24' font-weight='900' fill='white'%3EQA%3C/text%3E%3C/svg%3E">
"""

QA_BANNER = r"""
<div id="dv-qa-banner" class="dv-qa-banner" role="status" aria-label="Entorno QA de pruebas">
    <span class="dv-qa-banner__pill">QA</span>
    <span class="dv-qa-banner__text">ENTORNO DE PRUEBAS</span>
    <span class="dv-qa-banner__hint">Los cambios realizados aquí no modifican Producción.</span>
</div>
"""

_HTML_RE = re.compile(r"<html(?P<attrs>[^>]*)>", re.IGNORECASE)
_TITLE_RE = re.compile(
    r"(<title\b[^>]*>)(.*?)(</title>)",
    re.IGNORECASE | re.DOTALL,
)
_BODY_RE = re.compile(r"(<body\b[^>]*>)", re.IGNORECASE)


def _marcar_html_qa(html):
    if 'data-dv-env="qa"' not in html:
        html = _HTML_RE.sub(
            lambda match: (
                f'<html{match.group("attrs")} data-dv-env="qa">'
            ),
            html,
            count=1,
        )

    if "dv-qa-environment-style" not in html and "</head>" in html:
        html = html.replace("</head>", QA_HEAD + "\n</head>", 1)

    if "dv-qa-banner" not in html:
        html = _BODY_RE.sub(
            lambda match: match.group(1) + "\n" + QA_BANNER,
            html,
            count=1,
        )

    if "<title" in html.lower():
        def prefijar_titulo(match):
            titulo = match.group(2).strip()
            if titulo.upper().startswith("[QA]"):
                return match.group(0)
            titulo = titulo or "Doble V 3D"
            return f"{match.group(1)}[QA] {titulo}{match.group(3)}"

        html = _TITLE_RE.sub(prefijar_titulo, html, count=1)
    elif "</head>" in html:
        html = html.replace(
            "</head>",
            "<title>[QA] Doble V 3D</title>\n</head>",
            1,
        )

    return html


class EnvironmentVisualMiddleware:
    """Hace visualmente inequívoco el entorno QA en toda respuesta HTML."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not getattr(settings, "IS_QA", False):
            return response

        if getattr(response, "streaming", False):
            return response

        if "text/html" not in response.get("Content-Type", ""):
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        html = _marcar_html_qa(html)
        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
