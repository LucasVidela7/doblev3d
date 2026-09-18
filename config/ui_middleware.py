import json
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

DASHBOARD_KITS_STYLE = r"""
<style id="dv-dashboard-kits-style">
#dv-dashboard-kits.dv-kits-alerta{
    border-color:#e7bcbc;
}
#dv-dashboard-kits.dv-kits-alerta .accion-icono,
#dv-dashboard-kits.dv-kits-alerta .dv-dashboard-menu__icon{
    background:#fde5e5;
    color:#913434;
}
#dv-dashboard-kits.dv-dashboard-menu__link.dv-kits-alerta{
    border:1px solid #e7bcbc;
    background:#fff8f8;
}
#dv-dashboard-kits .dv-kits-aviso{
    margin-top:5px;
    color:#913434;
    font-size:10px;
    font-weight:900;
}
</style>
"""

KIT_ECONOMIA_STYLE = r"""
<style id="dv-kit-economia-style">
.dv-kit-economia{
    grid-column:1/-1;
    margin-top:10px;
    padding:11px 12px;
    border:1px solid #cfe2d5;
    border-radius:12px;
    background:#f0f9f3;
    color:#275c39;
    font-family:Arial,sans-serif;
    font-size:10px;
    line-height:1.45;
}
.dv-kit-economia.dv-kit-alerta{
    border-color:#e5b7b7;
    background:#fff0f0;
    color:#8e3434;
}
.dv-kit-economia-titulo{
    margin-bottom:4px;
    font-size:10px;
    font-weight:900;
    letter-spacing:.2px;
}
.dv-kit-economia-datos{
    font-weight:700;
}
.dv-kit-economia-motivo{
    margin-top:5px;
}
.dv-kit-economia-sugerido{
    margin-top:6px;
    font-weight:900;
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


def _datos_economicos_kits():
    from kits.models import Kit

    kits = list(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto")
        .order_by("nombre")
    )

    datos = {}
    alertas = 0

    for kit in kits:
        analisis = kit.analisis_economico
        if analisis["alerta"]:
            alertas += 1

        datos[str(kit.id)] = {
            "nombre": kit.nombre,
            "modalidad": kit.modalidad,
            "precio": str(kit.precio or 0),
            "tipo_calculo": analisis["tipo_calculo"],
            "costo_estimado": str(analisis["costo_estimado"]),
            "costo_peor_caso": str(analisis["costo_peor_caso"]),
            "margen_estimado": (
                str(analisis["margen_estimado"])
                if analisis["margen_estimado"] is not None
                else None
            ),
            "margen_peor_caso": (
                str(analisis["margen_peor_caso"])
                if analisis["margen_peor_caso"] is not None
                else None
            ),
            "precio_sugerido_minimo": str(
                analisis["precio_sugerido_minimo"]
            ),
            "margen_minimo": str(analisis["margen_minimo"]),
            "alerta": bool(analisis["alerta"]),
            "motivo": analisis["motivo"],
        }

    return datos, len(kits), alertas


def _dashboard_kits_html(total_kits, kits_alerta):
    kits_url = reverse("kits:lista")
    clase_alerta = " dv-kits-alerta" if kits_alerta else ""

    if kits_alerta:
        aviso = (
            f'<div class="dv-kits-aviso">⚠ {kits_alerta} '
            f'{"kit" if kits_alerta == 1 else "kits"} con precio para revisar</div>'
        )
        detalle_alerta = (
            f' ⚠ {kits_alerta} '
            f'{"kit" if kits_alerta == 1 else "kits"} con precio para revisar.'
        )
    else:
        aviso = ""
        detalle_alerta = ""

    descripcion = (
        f"{total_kits} "
        f'{"kit activo" if total_kits == 1 else "kits activos"}. '
        "Crear, editar y revisar rentabilidad."
        f"{detalle_alerta}"
    )

    return f"""
<script id="dv-dashboard-kits-script">
(function(){{
    var kitsUrl = {json.dumps(kits_url)};

    function enlaceExistente(contenedor){{
        var destino = new URL(kitsUrl, window.location.origin).pathname;
        return Array.from(contenedor.querySelectorAll('a')).find(function(link){{
            return link.pathname === destino;
        }}) || null;
    }}

    function enriquecerEnlace(enlace){{
        if (!enlace) return false;

        enlace.id = 'dv-dashboard-kits';
        enlace.setAttribute('data-dv-menu', 'kits');
        enlace.classList.toggle('dv-kits-alerta', {str(bool(False)).lower()});
        if ({kits_alerta} > 0) enlace.classList.add('dv-kits-alerta');

        var descripcionNodo = enlace.querySelector(
            '.accion-texto, .dv-dashboard-menu__description'
        );
        if (descripcionNodo){{
            descripcionNodo.textContent = {json.dumps(descripcion)};
        }}

        return true;
    }}

    function crearEnAcciones(acciones){{
        var existente = enlaceExistente(acciones);
        if (existente) return enriquecerEnlace(existente);

        var enlace = document.createElement('a');
        enlace.id = 'dv-dashboard-kits';
        enlace.href = kitsUrl;
        enlace.className = 'accion{clase_alerta}';
        enlace.innerHTML = `
            <div class="accion-icono">🧰</div>
            <div>
                <div class="accion-titulo">Kits</div>
                <div class="accion-texto">{descripcion}</div>
                {aviso}
            </div>
        `;
        acciones.appendChild(enlace);
        return true;
    }}

    function crearEnMenu(contenedor){{
        var existente = enlaceExistente(contenedor);
        if (existente) return enriquecerEnlace(existente);

        var enlace = document.createElement('a');
        enlace.id = 'dv-dashboard-kits';
        enlace.href = kitsUrl;
        enlace.className = 'dv-dashboard-menu__link{clase_alerta}';
        enlace.setAttribute('data-dv-menu', 'kits');

        var icono = document.createElement('span');
        icono.className = 'dv-dashboard-menu__icon';
        icono.textContent = '🧰';

        var contenido = document.createElement('span');

        var label = document.createElement('span');
        label.className = 'dv-dashboard-menu__label';
        label.textContent = 'Kits';
        contenido.appendChild(label);

        var descripcion = document.createElement('span');
        descripcion.className = 'dv-dashboard-menu__description';
        descripcion.textContent = {json.dumps(descripcion)};
        contenido.appendChild(descripcion);

        enlace.appendChild(icono);
        enlace.appendChild(contenido);
        contenedor.appendChild(enlace);
        return true;
    }}

    function agregarKits(){{
        var acciones = document.querySelector('.acciones');
        if (acciones) return crearEnAcciones(acciones);

        var menu = document.querySelector('.dv-dashboard-menu__links');
        if (menu) return crearEnMenu(menu);

        return false;
    }}

    function iniciar(){{
        if (agregarKits()) return;

        var intentos = 0;
        var timer = window.setInterval(function(){{
            intentos += 1;
            if (agregarKits() || intentos >= 20){{
                window.clearInterval(timer);
            }}
        }}, 50);
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""

def _kit_economia_html(datos_kits):
    datos_json = json.dumps(
        datos_kits,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    return f"""
<script id="dv-kit-economia-script">
(function(){{
    const datosKits = {datos_json};

    function moneda(valor){{
        return new Intl.NumberFormat('es-AR', {{
            maximumFractionDigits: 0
        }}).format(Number(valor || 0));
    }}

    function porcentaje(valor){{
        if (valor === null || valor === undefined || valor === '') return '—';
        return new Intl.NumberFormat('es-AR', {{
            minimumFractionDigits: 1,
            maximumFractionDigits: 1
        }}).format(Number(valor)) + '%';
    }}

    function escapar(texto){{
        const div = document.createElement('div');
        div.textContent = texto || '';
        return div.innerHTML;
    }}

    function tipoDelItem(select){{
        const item = select.closest('.item');
        if (!item) return 'KIT';

        const tipo = item.querySelector('select[id^="tipo_item_"]');
        return tipo ? tipo.value : 'KIT';
    }}

    function cajaPara(select){{
        const item = select.closest('.item');
        if (!item) return null;

        let caja = item.querySelector(
            `.dv-kit-economia[data-kit-select="${{select.id}}"]`
        );

        if (caja) return caja;

        caja = document.createElement('div');
        caja.className = 'dv-kit-economia';
        caja.dataset.kitSelect = select.id;
        caja.hidden = true;

        const ancla =
            select.closest('.selector-kit')
            || select.closest('.full.bloque-kit')
            || select.parentElement;

        if (ancla){{
            ancla.insertAdjacentElement('afterend', caja);
        }}

        return caja;
    }}

    function actualizar(select){{
        const caja = cajaPara(select);
        if (!caja) return;

        if (tipoDelItem(select) !== 'KIT' || !select.value){{
            caja.hidden = true;
            return;
        }}

        const info = datosKits[String(select.value)];
        if (!info){{
            caja.hidden = true;
            return;
        }}

        caja.hidden = false;
        caja.classList.toggle('dv-kit-alerta', !!info.alerta);

        const titulo = info.alerta
            ? '⚠ REVISAR PRECIO DEL KIT'
            : '✓ RENTABILIDAD DEL KIT';

        let datos;
        if (info.modalidad === 'FIJO'){{
            datos =
                `Precio $${{moneda(info.precio)}} · `
                + `costo actual $${{moneda(info.costo_estimado)}} · `
                + `margen ${{porcentaje(info.margen_estimado)}}`;
        }} else {{
            datos =
                `Precio $${{moneda(info.precio)}} · `
                + `costo estimado $${{moneda(info.costo_estimado)}} · `
                + `margen estimado ${{porcentaje(info.margen_estimado)}} · `
                + `peor combinación ${{porcentaje(info.margen_peor_caso)}}`;
        }}

        let html =
            `<div class="dv-kit-economia-titulo">${{titulo}}</div>`
            + `<div class="dv-kit-economia-datos">${{datos}}</div>`;

        if (info.alerta && info.motivo){{
            html +=
                `<div class="dv-kit-economia-motivo">${{escapar(info.motivo)}}</div>`;
        }}

        if (
            info.alerta
            && Number(info.precio_sugerido_minimo || 0) > 0
        ){{
            html +=
                `<div class="dv-kit-economia-sugerido">`
                + `Sugerido desde $${{moneda(info.precio_sugerido_minimo)}} `
                + `para sostener ${{porcentaje(info.margen_minimo)}} de margen.`
                + `</div>`;
        }}

        if (caja.innerHTML !== html){{
            caja.innerHTML = html;
        }}
    }}

    function instalar(select){{
        if (!select || select.dataset.dvKitEconomia === '1'){{
            if (select) actualizar(select);
            return;
        }}

        select.dataset.dvKitEconomia = '1';
        select.addEventListener('change', function(){{
            actualizar(select);
        }});
        actualizar(select);
    }}

    function buscarEn(nodo){{
        if (!nodo || nodo.nodeType !== 1) return;

        if (nodo.matches && nodo.matches('select[id^="kit_"]')){{
            instalar(nodo);
        }}

        if (nodo.querySelectorAll){{
            nodo.querySelectorAll('select[id^="kit_"]').forEach(instalar);
        }}
    }}

    function iniciar(){{
        document.querySelectorAll('select[id^="kit_"]').forEach(instalar);

        document.addEventListener('change', function(evento){{
            const objetivo = evento.target;
            if (!objetivo || !objetivo.matches) return;

            if (objetivo.matches('select[id^="tipo_item_"]')){{
                const item = objetivo.closest('.item');
                if (!item) return;
                const kitSelect = item.querySelector('select[id^="kit_"]');
                if (kitSelect) actualizar(kitSelect);
            }}
        }});

        const observador = new MutationObserver(function(mutaciones){{
            mutaciones.forEach(function(mutacion){{
                mutacion.addedNodes.forEach(buscarEn);
            }});
        }});

        observador.observe(document.body, {{
            childList: true,
            subtree: true
        }});
    }}

    if (document.readyState === 'loading'){{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
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
        view_name = (
            resolver_match.view_name
            if resolver_match is not None
            else ""
        )

        es_dashboard = view_name == "dashboard:inicio"
        es_pedido_con_kits = view_name in {
            "pedidos:nuevo",
            "pedidos:editar",
        }

        datos_kits = None
        total_kits = 0
        kits_alerta = 0

        if es_dashboard or es_pedido_con_kits:
            datos_kits, total_kits, kits_alerta = _datos_economicos_kits()

        if (
            es_dashboard
            and request.user.is_authenticated
            and "dv-dashboard-session" not in html
        ):
            if "</head>" in html:
                html = html.replace(
                    "</head>",
                    DASHBOARD_SESSION_STYLE + DASHBOARD_KITS_STYLE + "\n</head>",
                    1,
                )
            if "</body>" in html:
                html = html.replace(
                    "</body>",
                    _dashboard_session_html(request)
                    + _dashboard_kits_html(total_kits, kits_alerta)
                    + "\n</body>",
                    1,
                )

        if (
            es_pedido_con_kits
            and datos_kits is not None
            and "dv-kit-economia-script" not in html
        ):
            if "</head>" in html and "dv-kit-economia-style" not in html:
                html = html.replace(
                    "</head>",
                    KIT_ECONOMIA_STYLE + "\n</head>",
                    1,
                )

            if "</body>" in html:
                html = html.replace(
                    "</body>",
                    _kit_economia_html(datos_kits) + "\n</body>",
                    1,
                )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
