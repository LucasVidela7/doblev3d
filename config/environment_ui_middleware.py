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
    bottom:calc(92px + env(safe-area-inset-bottom, 0px));
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


@media(max-width:640px){
    html[data-dv-env="qa"] body::after{
        right:8px;
        bottom:calc(84px + env(safe-area-inset-bottom, 0px));
        width:48px;
        height:48px;
        border-radius:15px;
        font-size:17px;
    }
}
</style>
<link id="dv-qa-favicon" rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%237c3aed'/%3E%3Ctext x='32' y='41' text-anchor='middle' font-family='Arial' font-size='24' font-weight='900' fill='white'%3EQA%3C/text%3E%3C/svg%3E">
"""

DASHBOARD_MENU_HEAD = r"""
<style id="dv-dashboard-menu-style">
.dv-dashboard-menu-toggle,
.dv-dashboard-menu,
.dv-dashboard-menu-overlay{
    font-family:Arial,sans-serif;
}

.dv-dashboard-menu-toggle{
    position:fixed;
    top:62px;
    right:14px;
    z-index:160;
    width:48px;
    height:48px;
    display:none;
    align-items:center;
    justify-content:center;
    border:1px solid rgba(36,39,43,.12);
    border-radius:15px;
    background:#24272b;
    color:#fff;
    box-shadow:0 8px 24px rgba(20,25,35,.2);
    cursor:pointer;
}

.dv-dashboard-menu-toggle__icon{
    width:21px;
    display:grid;
    gap:4px;
}

.dv-dashboard-menu-toggle__icon span{
    display:block;
    height:2px;
    border-radius:999px;
    background:currentColor;
}

.dv-dashboard-menu{
    position:fixed;
    z-index:150;
    top:22px;
    right:18px;
    bottom:104px;
    width:272px;
    display:flex;
    flex-direction:column;
    overflow:hidden;
    border:1px solid #e5e7eb;
    border-radius:20px;
    background:rgba(255,255,255,.97);
    box-shadow:0 14px 42px rgba(20,25,35,.13);
    backdrop-filter:blur(14px);
}

.dv-dashboard-menu__header{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    padding:17px 16px 13px;
    border-bottom:1px solid #eceef1;
}

.dv-dashboard-menu__title{
    margin:0;
    font-size:15px;
    font-weight:900;
    color:#24272b;
}

.dv-dashboard-menu__hint{
    margin-top:3px;
    color:#73777f;
    font-size:9px;
    font-weight:700;
    letter-spacing:.2px;
}

.dv-dashboard-menu__close{
    display:none;
    width:38px;
    height:38px;
    border:0;
    border-radius:12px;
    background:#f0f1f3;
    color:#24272b;
    font-size:22px;
    cursor:pointer;
}

.dv-dashboard-menu__links{
    min-height:0;
    overflow-y:auto;
    padding:9px;
}

.dv-dashboard-menu__link{
    display:grid;
    grid-template-columns:40px minmax(0,1fr);
    align-items:center;
    gap:10px;
    min-height:58px;
    padding:9px 10px;
    border-radius:14px;
    color:#24272b;
    text-decoration:none;
    transition:background .12s ease,transform .12s ease;
}

.dv-dashboard-menu__link:hover{
    background:#f4f5f7;
}

.dv-dashboard-menu__link:active{
    transform:scale(.985);
}

.dv-dashboard-menu__link--principal{
    background:#24272b;
    color:#fff;
    margin-bottom:5px;
}

.dv-dashboard-menu__link--principal:hover{
    background:#30343a;
}

.dv-dashboard-menu__icon{
    width:40px;
    height:40px;
    display:grid;
    place-items:center;
    border-radius:12px;
    background:#eef0f3;
    font-size:18px;
}

.dv-dashboard-menu__link--principal .dv-dashboard-menu__icon{
    background:rgba(255,255,255,.14);
}

.dv-dashboard-menu__label{
    min-width:0;
    font-size:12px;
    font-weight:900;
    line-height:1.15;
}

.dv-dashboard-menu__description{
    display:none;
    margin-top:3px;
    color:#73777f;
    font-size:10px;
    line-height:1.3;
}

.dv-dashboard-menu__link--principal .dv-dashboard-menu__description{
    color:#d7d9dd;
}

.dv-dashboard-menu-overlay{
    position:fixed;
    inset:0;
    z-index:140;
    display:none;
    background:rgba(24,27,31,.4);
    backdrop-filter:blur(2px);
}

html.dv-dashboard-menu-open{
    overflow:hidden;
}

@media(min-width:1180px){
    body.dv-dashboard-menu-ready{
        padding-right:308px!important;
    }

    body.dv-dashboard-menu-ready .contenedor{
        width:min(1420px,calc(100% - 36px))!important;
        max-width:none!important;
        margin-left:auto!important;
        margin-right:auto!important;
    }

    .dv-dashboard-menu{
        border-radius:22px;
        box-shadow:0 16px 44px rgba(20,25,35,.11);
    }

    .dv-dashboard-menu__header{
        padding:18px 16px 14px;
    }

    .dv-dashboard-menu__links{
        padding:10px;
    }

    .dv-dashboard-menu__link{
        min-height:56px;
        border-radius:13px;
    }
}

@media(max-width:1179px){
    .dv-dashboard-menu-toggle{
        display:flex;
    }

    .dv-dashboard-menu{
        top:0;
        right:0;
        bottom:0;
        width:min(360px,90vw);
        border-radius:22px 0 0 22px;
        transform:translateX(105%);
        transition:transform .2s ease;
        z-index:170;
    }

    .dv-dashboard-menu.is-open{
        transform:translateX(0);
    }

    .dv-dashboard-menu.is-open + .dv-dashboard-menu-overlay{
        display:block;
    }

    .dv-dashboard-menu__header{
        padding:18px 16px;
    }

    .dv-dashboard-menu__close{
        display:grid;
        place-items:center;
    }

    .dv-dashboard-menu__links{
        padding:10px 11px 110px;
    }

    .dv-dashboard-menu__link{
        min-height:68px;
        grid-template-columns:46px minmax(0,1fr);
        gap:11px;
        padding:10px;
    }

    .dv-dashboard-menu__icon{
        width:46px;
        height:46px;
        font-size:20px;
    }

    .dv-dashboard-menu__label{
        font-size:13px;
    }

    .dv-dashboard-menu__description{
        display:block;
    }
}

@media(max-width:640px){
    .dv-dashboard-menu-toggle{
        top:58px;
        right:10px;
        width:44px;
        height:44px;
        border-radius:14px;
    }

    .dv-dashboard-menu{
        width:min(340px,92vw);
    }
}
</style>
"""

DASHBOARD_MENU_SCRIPT = r"""
<script id="dv-dashboard-menu-script">
(function(){
    function texto(el, selector){
        var nodo = el.querySelector(selector);
        return nodo ? nodo.textContent.replace(/\s+/g,' ').trim() : '';
    }

    function iniciar(){
        if (document.getElementById('dv-dashboard-menu')) return;

        var secciones = Array.from(document.querySelectorAll('section.seccion'));
        var acciones = secciones.find(function(section){
            var titulo = section.querySelector('.seccion-titulo');
            return titulo && titulo.textContent.replace(/\s+/g,' ').trim().toLowerCase() === 'acciones rápidas';
        });
        if (!acciones) return;

        var linksOrigen = Array.from(acciones.querySelectorAll('.acciones > a.accion'));
        if (!linksOrigen.length) return;

        var menu = document.createElement('aside');
        menu.id = 'dv-dashboard-menu';
        menu.className = 'dv-dashboard-menu';
        menu.setAttribute('aria-label','Menú de gestión');

        var header = document.createElement('div');
        header.className = 'dv-dashboard-menu__header';
        header.innerHTML = '<div><h2 class="dv-dashboard-menu__title">Menú</h2><div class="dv-dashboard-menu__hint">Accesos de gestión</div></div><button type="button" class="dv-dashboard-menu__close" aria-label="Cerrar menú">×</button>';

        var links = document.createElement('nav');
        links.className = 'dv-dashboard-menu__links';

        linksOrigen.forEach(function(origen, indice){
            var link = document.createElement('a');
            link.href = origen.href;
            link.className = 'dv-dashboard-menu__link' + (origen.classList.contains('accion-principal') ? ' dv-dashboard-menu__link--principal' : '');

            if (origen.id === 'dv-dashboard-kits') {
                link.id = 'dv-dashboard-kits';
                link.setAttribute('data-dv-menu', 'kits');
                if (origen.classList.contains('dv-kits-alerta')) {
                    link.classList.add('dv-kits-alerta');
                }
            }

            var icono = document.createElement('span');
            icono.className = 'dv-dashboard-menu__icon';
            icono.textContent = texto(origen,'.accion-icono') || '•';

            var contenido = document.createElement('span');
            var label = document.createElement('span');
            label.className = 'dv-dashboard-menu__label';
            label.textContent = texto(origen,'.accion-titulo') || ('Acceso ' + (indice + 1));
            contenido.appendChild(label);

            var descripcionTexto = texto(origen,'.accion-texto');
            if (descripcionTexto){
                var descripcion = document.createElement('span');
                descripcion.className = 'dv-dashboard-menu__description';
                descripcion.textContent = descripcionTexto;
                contenido.appendChild(descripcion);
            }

            link.appendChild(icono);
            link.appendChild(contenido);
            links.appendChild(link);
        });

        menu.appendChild(header);
        menu.appendChild(links);

        var overlay = document.createElement('div');
        overlay.className = 'dv-dashboard-menu-overlay';
        overlay.setAttribute('aria-hidden','true');

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'dv-dashboard-menu-toggle';
        toggle.setAttribute('aria-label','Abrir menú');
        toggle.setAttribute('aria-controls','dv-dashboard-menu');
        toggle.setAttribute('aria-expanded','false');
        toggle.innerHTML = '<span class="dv-dashboard-menu-toggle__icon" aria-hidden="true"><span></span><span></span><span></span></span>';

        function abrir(){
            menu.classList.add('is-open');
            document.documentElement.classList.add('dv-dashboard-menu-open');
            toggle.setAttribute('aria-expanded','true');
            var primero = menu.querySelector('a,button');
            if (primero) primero.focus({preventScroll:true});
        }

        function cerrar(){
            menu.classList.remove('is-open');
            document.documentElement.classList.remove('dv-dashboard-menu-open');
            toggle.setAttribute('aria-expanded','false');
        }

        toggle.addEventListener('click',function(){
            if (menu.classList.contains('is-open')) cerrar(); else abrir();
        });
        overlay.addEventListener('click',cerrar);
        header.querySelector('.dv-dashboard-menu__close').addEventListener('click',cerrar);
        document.addEventListener('keydown',function(event){
            if (event.key === 'Escape') cerrar();
        });
        window.addEventListener('resize',function(){
            if (window.innerWidth >= 1180) cerrar();
        });

        acciones.remove();
        document.body.appendChild(toggle);
        document.body.appendChild(menu);
        document.body.appendChild(overlay);
        document.body.classList.add('dv-dashboard-menu-ready');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded',iniciar);
    } else {
        iniciar();
    }
})();
</script>
"""

_HTML_RE = re.compile(r"<html(?P<attrs>[^>]*)>", re.IGNORECASE)
_TITLE_RE = re.compile(
    r"(<title\b[^>]*>)(.*?)(</title>)",
    re.IGNORECASE | re.DOTALL,
)


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


def _inyectar_menu_dashboard(html):
    """Compatibilidad: el menú ahora vive en shared/navigation.html."""
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

        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""
        if view_name == "dashboard:inicio":
            html = _inyectar_menu_dashboard(html)

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
