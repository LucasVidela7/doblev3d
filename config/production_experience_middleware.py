"""Mejoras de experiencia para Producción e Impresiones por producto.

Este middleware sólo afecta la presentación. La validación de concurrencia de
impresoras continúa en ``produccion.views.iniciar_produccion`` para evitar que
una carrera entre dos usuarios pueda iniciar dos trabajos en la misma máquina.
"""

import json

from produccion.models import Produccion


PRODUCCION_STYLE = r"""
<style id="dv-produccion-experiencia-style">
.dv-produccion-seccion{
    margin-top:12px;
}
.dv-produccion-seccion-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin:0 0 8px;
}
.dv-produccion-seccion-titulo{
    margin:0;
    font-size:11px;
    font-weight:900;
    letter-spacing:.35px;
    color:#4f555d;
}
.dv-produccion-seccion-meta{
    display:flex;
    flex-wrap:wrap;
    justify-content:flex-end;
    gap:5px;
}
.dv-produccion-chip{
    display:inline-flex;
    align-items:center;
    min-height:24px;
    padding:0 8px;
    border-radius:999px;
    background:#eef0f3;
    color:#5b6169;
    font-size:7px;
    font-weight:900;
}
.dv-produccion-chip.imprimiendo{
    background:#e3efff;
    color:#245a9b;
}
.dv-produccion-chip.planificada{
    background:#fff2c7;
    color:#765b00;
}
.dv-impresora-no-disponible{
    margin-top:5px;
    padding:7px 9px;
    border-radius:8px;
    background:#fff2f2;
    color:#8f3434;
    font-size:7px;
    font-weight:900;
    line-height:1.35;
}
.selector-impresora-inicio option:disabled{
    color:#9b4b4b;
}
.dv-finalizadas{
    margin-top:14px;
    border:1px solid #dfe3e8;
    border-radius:15px;
    background:#fff;
    box-shadow:0 2px 10px rgba(20,25,35,.04);
    overflow:hidden;
}
.dv-finalizadas > summary{
    list-style:none;
    display:grid;
    grid-template-columns:minmax(0,1fr) auto auto;
    align-items:center;
    gap:10px;
    min-height:52px;
    padding:10px 13px;
    cursor:pointer;
    user-select:none;
    background:#f7f8fa;
}
.dv-finalizadas > summary::-webkit-details-marker{display:none}
.dv-finalizadas-titulo{
    min-width:0;
    font-size:10px;
    font-weight:900;
    color:#4f555d;
}
.dv-finalizadas-subtitulo{
    display:block;
    margin-top:2px;
    color:#858a91;
    font-size:7px;
    font-weight:700;
}
.dv-finalizadas-contador{
    display:inline-flex;
    align-items:center;
    min-height:25px;
    padding:0 8px;
    border-radius:999px;
    background:#dff4e5;
    color:#24633a;
    font-size:7px;
    font-weight:900;
}
.dv-finalizadas-flecha{
    width:24px;
    height:24px;
    display:grid;
    place-items:center;
    border-radius:50%;
    background:#eceef1;
    color:#555b63;
    font-size:12px;
    transition:transform .18s ease;
}
.dv-finalizadas[open] .dv-finalizadas-flecha{
    transform:rotate(180deg);
}
.dv-finalizadas-cuerpo{
    padding:8px;
    border-top:1px solid #e8eaed;
}
.dv-finalizadas .tabla-contenedor{
    margin:0;
    box-shadow:none;
    border-color:#eceef1;
}
.dv-finalizadas tbody tr{
    opacity:.86;
}
.dv-finalizadas tbody tr:hover{
    opacity:1;
}
.dv-finalizadas .estado-fijo{
    min-height:34px;
}
.dv-finalizadas .btn-repetir{
    min-height:31px;
}
@media(max-width:900px){
    .dv-produccion-seccion-head{
        align-items:flex-start;
        flex-direction:column;
        gap:6px;
    }
    .dv-produccion-seccion-meta{
        justify-content:flex-start;
    }
    .dv-finalizadas > summary{
        grid-template-columns:minmax(0,1fr) auto auto;
    }
    .dv-finalizadas-cuerpo{
        padding:7px 0 0;
        background:#f4f5f7;
    }
    .dv-finalizadas .tabla-contenedor{
        border:0;
        background:transparent;
    }
}
@media(max-width:560px){
    .dv-finalizadas > summary{
        min-height:58px;
        padding:10px 11px;
    }
    .dv-finalizadas-subtitulo{
        max-width:220px;
    }
}
</style>
"""


PLANIFICACION_STYLE = r"""
<style id="dv-planificacion-experiencia-style">
/* Los paneles de planificación deben usar todo el ancho de su tarjeta. */
.dv-planificar-celda{
    align-items:stretch!important;
}
.dv-planificar-celda > *,
.dv-personalizados,
.dv-personalizado,
.dv-plan-details,
.dv-plan-form{
    width:100%!important;
    max-width:none!important;
}
.dv-plan-details > summary{
    min-height:40px;
    display:flex;
    align-items:center;
}

/* En tablet horizontal evitamos el formulario alto y angosto de las capturas. */
@media(min-width:651px) and (max-width:1100px){
    .dv-plan-form{
        grid-template-columns:110px minmax(210px,1.2fr) minmax(185px,.9fr)!important;
        align-items:end!important;
        gap:8px!important;
        padding:10px!important;
    }
    .dv-plan-fecha,
    .dv-plan-duracion{
        grid-column:auto!important;
    }
    .dv-plan-duracion{
        display:grid!important;
        grid-template-columns:1fr 1fr!important;
        gap:7px!important;
    }
    .dv-plan-tiempo,
    .dv-plan-enviar{
        grid-column:1/-1!important;
    }
    .dv-plan-campo input{
        min-height:40px!important;
        font-size:11px!important;
    }
    .dv-plan-enviar{
        min-height:40px!important;
    }
}

@media(max-width:650px){
    .dv-plan-form{
        grid-template-columns:1fr!important;
        gap:7px!important;
    }
    .dv-plan-fecha,
    .dv-plan-duracion,
    .dv-plan-tiempo,
    .dv-plan-enviar{
        grid-column:1!important;
    }
    .dv-plan-duracion{
        grid-template-columns:1fr 1fr!important;
    }
}
</style>
"""


def _impresoras_ocupadas():
    """Devuelve una descripción compacta de las impresoras imprimiendo."""
    ocupadas = {}
    trabajos = (
        Produccion.objects
        .filter(estado="IMPRIMIENDO", impresora__isnull=False)
        .select_related("impresora", "producto")
        .order_by("id")
    )

    for trabajo in trabajos:
        clave = str(trabajo.impresora_id)
        if clave in ocupadas:
            continue
        ocupadas[clave] = {
            "codigo": trabajo.codigo,
            "producto": trabajo.producto.nombre,
        }

    return ocupadas


def _script_produccion(ocupadas):
    ocupadas_json = json.dumps(
        ocupadas,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    return f"""
<script id="dv-produccion-experiencia-script">
(function(){{
    const ocupadas = {ocupadas_json};

    function bloquearImpresorasOcupadas(){{
        document.querySelectorAll('.selector-impresora-inicio').forEach(function(select){{
            let libres = 0;

            Array.from(select.options).forEach(function(opcion){{
                if (!opcion.value) return;
                const trabajo = ocupadas[String(opcion.value)];
                if (!trabajo){{
                    libres += 1;
                    return;
                }}

                opcion.disabled = true;
                opcion.dataset.dvOcupada = '1';
                if (opcion.textContent.indexOf('OCUPADA') === -1){{
                    opcion.textContent = opcion.textContent.trim()
                        + ' · OCUPADA (' + trabajo.codigo + ')';
                }}
            }});

            const form = select.closest('.inicio-produccion-form');
            if (!form) return;
            const boton = form.querySelector('.btn-iniciar');

            if (libres === 0){{
                select.value = '';
                select.disabled = true;
                if (boton) boton.disabled = true;

                if (!form.querySelector('.dv-impresora-no-disponible')){{
                    const aviso = document.createElement('div');
                    aviso.className = 'dv-impresora-no-disponible';
                    aviso.textContent = 'Todas las impresoras están ocupadas. Finalizá una impresión para liberar una máquina.';
                    form.appendChild(aviso);
                }}
            }}
        }});
    }}

    function separarFinalizadas(){{
        const contenedor = document.querySelector('.tabla-contenedor');
        const tabla = contenedor && contenedor.querySelector('table');
        if (!contenedor || !tabla || tabla.dataset.dvSeparada === '1') return;

        const tbody = tabla.querySelector('tbody');
        if (!tbody) return;

        const filas = Array.from(tbody.querySelectorAll(':scope > tr'));
        const finalizadas = filas.filter(function(fila){{
            return !!fila.querySelector('.estado-LISTO');
        }});
        if (!finalizadas.length){{
            tabla.dataset.dvSeparada = '1';
            return;
        }}

        const activas = filas.filter(function(fila){{
            return finalizadas.indexOf(fila) === -1;
        }});
        const imprimiendo = activas.filter(function(fila){{
            return !!fila.querySelector('.estado-IMPRIMIENDO');
        }}).length;
        const planificadas = Math.max(activas.length - imprimiendo, 0);

        const padre = contenedor.parentNode;
        const seccion = document.createElement('section');
        seccion.className = 'dv-produccion-seccion';
        seccion.innerHTML = `
            <div class="dv-produccion-seccion-head">
                <h2 class="dv-produccion-seccion-titulo">EN CURSO</h2>
                <div class="dv-produccion-seccion-meta">
                    <span class="dv-produccion-chip imprimiendo">● IMPRIMIENDO ${{imprimiendo}}</span>
                    <span class="dv-produccion-chip planificada">◷ PLANIFICADAS ${{planificadas}}</span>
                </div>
            </div>
        `;
        padre.insertBefore(seccion, contenedor);
        seccion.appendChild(contenedor);

        const detalles = document.createElement('details');
        detalles.className = 'dv-finalizadas';
        detalles.innerHTML = `
            <summary>
                <span class="dv-finalizadas-titulo">
                    ✓ FINALIZADAS
                    <span class="dv-finalizadas-subtitulo">Historial reciente. Está colapsado para priorizar el trabajo pendiente.</span>
                </span>
                <span class="dv-finalizadas-contador">${{finalizadas.length}}</span>
                <span class="dv-finalizadas-flecha">⌄</span>
            </summary>
            <div class="dv-finalizadas-cuerpo"></div>
        `;

        const tablaFinal = tabla.cloneNode(false);
        tablaFinal.removeAttribute('data-dv-separada');
        const cabecera = tabla.querySelector('thead');
        if (cabecera) tablaFinal.appendChild(cabecera.cloneNode(true));
        const bodyFinal = document.createElement('tbody');
        finalizadas.forEach(function(fila){{ bodyFinal.appendChild(fila); }});
        tablaFinal.appendChild(bodyFinal);

        const contenedorFinal = document.createElement('div');
        contenedorFinal.className = 'tabla-contenedor dv-tabla-finalizadas';
        contenedorFinal.appendChild(tablaFinal);
        detalles.querySelector('.dv-finalizadas-cuerpo').appendChild(contenedorFinal);
        seccion.insertAdjacentElement('afterend', detalles);

        const estado = new URLSearchParams(window.location.search).get('estado') || 'OPERATIVA';
        if (estado === 'LISTO' || activas.length === 0){{
            detalles.open = true;
            seccion.hidden = true;
        }}

        tabla.dataset.dvSeparada = '1';
    }}

    function iniciar(){{
        bloquearImpresorasOcupadas();
        separarFinalizadas();
    }}

    if (document.readyState === 'loading'){{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""


PLANIFICACION_SCRIPT = r"""
<script id="dv-planificacion-experiencia-script">
(function(){
    function ajustar(){
        document.querySelectorAll('.dv-plan-form').forEach(function(form){
            const cantidad = form.querySelector('input[name="cantidad"]');
            if (!cantidad) return;

            /*
             * La producción estándar es deliberadamente libre: se puede
             * superar A imprimir para fabricar stock. Los personalizados sí
             * conservan el máximo exacto del pedido.
             */
            if (!form.querySelector('input[name="personalizado_id"]')){
                cantidad.removeAttribute('max');
                cantidad.dataset.dvCantidadLibre = '1';
            }
        });
    }

    function iniciar(){
        /* OperacionesUIMiddleware crea estos formularios al cargar el DOM. */
        window.setTimeout(ajustar, 0);
        new MutationObserver(function(){
            window.setTimeout(ajustar, 0);
        }).observe(document.body, {childList:true, subtree:true});
    }

    if (document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
</script>
"""


class ProductionExperienceMiddleware:
    """Mejora lectura y acciones de las pantallas operativas de producción."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""

        if (
            getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
            or response.status_code != 200
        ):
            return response

        if view_name not in {
            "produccion:lista",
            "pedidos:impresiones_productos",
        }:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if view_name == "produccion:lista":
            if "dv-produccion-experiencia-style" not in html and "</head>" in html:
                html = html.replace(
                    "</head>",
                    PRODUCCION_STYLE + "\n</head>",
                    1,
                )
            if "dv-produccion-experiencia-script" not in html and "</body>" in html:
                html = html.replace(
                    "</body>",
                    _script_produccion(_impresoras_ocupadas()) + "\n</body>",
                    1,
                )

        if view_name == "pedidos:impresiones_productos":
            if "dv-planificacion-experiencia-style" not in html and "</head>" in html:
                html = html.replace(
                    "</head>",
                    PLANIFICACION_STYLE + "\n</head>",
                    1,
                )
            if "dv-planificacion-experiencia-script" not in html and "</body>" in html:
                html = html.replace(
                    "</body>",
                    PLANIFICACION_SCRIPT + "\n</body>",
                    1,
                )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
