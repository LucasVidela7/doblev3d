import json
from html import escape

from django.contrib import messages
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.urls import reverse

from productos.models import Producto


ORDENES_STYLE = r"""
<style id="dv-ordenes-productos-style">
.dv-sin-piezas-aviso{
    margin-top:5px;
    color:#747980;
    font-size:8px;
    line-height:1.35;
}
</style>
"""

TIPOS_STYLE = r"""
<style id="dv-tipos-producto-style">
.dv-tipo-wrap{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;align-items:end}
.dv-tipo-nuevo-btn{min-height:49px;padding:0 12px;border:1px solid #d5d8dd;border-radius:11px;background:#fff;color:#345f91;font-size:9px;font-weight:900;cursor:pointer;white-space:nowrap}
.dv-tipo-nuevo{display:none;grid-column:1/-1;grid-template-columns:minmax(0,1fr) auto;gap:7px;margin-top:2px;padding:9px;border:1px solid #d7e5f5;border-radius:11px;background:#f8fbff}
.dv-tipo-nuevo.activo{display:grid}
.dv-tipo-crear{min-height:43px;padding:0 12px;border:0;border-radius:9px;background:#24272b;color:#fff;font-size:9px;font-weight:900;cursor:pointer}
.dv-tipo-estado{grid-column:1/-1;min-height:12px;color:#747980;font-size:8px;font-weight:700}
.dv-tipo-estado.error{color:#9a3030}
@media(max-width:600px){.dv-tipo-wrap{grid-template-columns:1fr}.dv-tipo-nuevo{grid-template-columns:1fr}.dv-tipo-nuevo-btn,.dv-tipo-crear{width:100%}}
</style>
"""

PLAN_STYLE = r"""
<style id="dv-planificar-productos-style">
.dv-planificar-celda{min-width:245px;vertical-align:top!important}
.dv-plan-resumen{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px}
.dv-plan-chip{display:inline-flex;padding:4px 7px;border-radius:999px;background:#eef0f3;color:#5d6269;font-size:7px;font-weight:900}
.dv-plan-chip.activo{background:#e3efff;color:#245a9b}
.dv-plan-details{border:1px solid #dfe2e6;border-radius:10px;background:#fff;margin-top:6px;overflow:hidden}
.dv-plan-details>summary{list-style:none;padding:9px 10px;cursor:pointer;font-size:8px;font-weight:900;color:#333}
.dv-plan-details>summary::-webkit-details-marker{display:none}
.dv-plan-form{display:grid;grid-template-columns:78px minmax(145px,1fr);gap:7px;padding:9px;border-top:1px solid #eceef1;background:#fafbfc}
.dv-plan-campo label{display:block;margin-bottom:3px;color:#747980;font-size:7px;font-weight:900}
.dv-plan-campo input{width:100%;min-height:36px;padding:5px 7px;border:1px solid #d6d9de;border-radius:8px;background:#fff;font-size:10px}
.dv-plan-fecha{grid-column:2}
.dv-plan-duracion{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;gap:7px}
.dv-plan-tiempo{grid-column:1/-1;color:#747980;font-size:7px;line-height:1.35}
.dv-plan-enviar{grid-column:1/-1;min-height:36px;border:0;border-radius:8px;background:#24272b;color:#fff;font-size:8px;font-weight:900;cursor:pointer}
.dv-personalizados{margin-top:7px;padding:8px;border:1px solid #efd9a6;border-radius:10px;background:#fffaf0}
.dv-personalizados-titulo{color:#856404;font-size:8px;font-weight:900;margin-bottom:5px}
.dv-personalizado{padding:7px 0;border-top:1px solid #f0e4c5}
.dv-personalizado:first-of-type{border-top:0}
.dv-personalizado strong{display:block;font-size:9px}
.dv-personalizado-meta{margin-top:3px;color:#765b00;font-size:7px;line-height:1.4}
.dv-plan-vacio{color:#8a8f96;font-size:8px;line-height:1.4}
@media(max-width:800px){.dv-planificar-celda{min-width:230px}.dv-plan-form{grid-template-columns:1fr}.dv-plan-fecha,.dv-plan-duracion{grid-column:1}.dv-plan-duracion{grid-template-columns:1fr 1fr}}
</style>
"""


def _piezas_ids():
    return list(
        Producto.objects
        .filter(solo_produccion=True)
        .values_list("id", flat=True)
    )


def _ids_productos_post(request):
    ids = set()

    for clave in request.POST.keys():
        if not (
            clave.startswith("producto_")
            or clave.startswith("productos_kit_")
        ):
            continue

        for valor in request.POST.getlist(clave):
            texto = str(valor or "").strip()
            if texto.isdigit():
                ids.add(int(texto))

    return ids


def _script_sin_piezas(ids_piezas):
    ids_json = json.dumps([str(valor) for valor in ids_piezas])

    return f"""
<script id="dv-ordenes-productos-script">
(function(){{
    const piezas = new Set({ids_json});
    const selector = [
        'select[name^="producto_"]',
        'select[name^="productos_kit_"]'
    ].join(',');

    function limpiar(raiz){{
        const selects = [];
        if (raiz && raiz.matches && raiz.matches(selector)) selects.push(raiz);
        if (raiz && raiz.querySelectorAll){{
            raiz.querySelectorAll(selector).forEach(function(select){{
                selects.push(select);
            }});
        }}

        selects.forEach(function(select){{
            select.querySelectorAll('option').forEach(function(opcion){{
                if (piezas.has(String(opcion.value))) opcion.remove();
            }});

            const contenedor = select.closest('.campo, .full, div');
            if (
                contenedor
                && !contenedor.querySelector('.dv-sin-piezas-aviso')
                && select.name.indexOf('producto_') === 0
            ) {{
                const aviso = document.createElement('div');
                aviso.className = 'dv-sin-piezas-aviso';
                aviso.textContent = 'Solo productos comerciales. Las piezas internas se gestionan desde Producción.';
                contenedor.appendChild(aviso);
            }}
        }});
    }}

    function iniciar(){{
        limpiar(document);
        new MutationObserver(function(cambios){{
            cambios.forEach(function(cambio){{
                cambio.addedNodes.forEach(function(nodo){{
                    if (nodo.nodeType === 1) limpiar(nodo);
                }});
            }});
        }}).observe(document.body, {{childList:true, subtree:true}});
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""


def _script_nuevo_tipo():
    url = reverse("productos:crear_tipo")
    url_json = json.dumps(url)

    return f"""
<script id="dv-tipos-producto-script">
(function(){{
    const urlCrear = {url_json};

    function iniciar(){{
        const select = document.querySelector('select[name="tipo"]');
        if (!select || select.dataset.dvTipos === '1') return;
        select.dataset.dvTipos = '1';

        const padre = select.parentElement;
        if (!padre) return;

        const wrap = document.createElement('div');
        wrap.className = 'dv-tipo-wrap';
        padre.insertBefore(wrap, select);
        wrap.appendChild(select);

        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'dv-tipo-nuevo-btn';
        boton.textContent = '＋ NUEVO TIPO';
        wrap.appendChild(boton);

        const panel = document.createElement('div');
        panel.className = 'dv-tipo-nuevo';
        panel.innerHTML = `
            <input type="text" class="dv-tipo-nombre" placeholder="Nombre del nuevo tipo">
            <button type="button" class="dv-tipo-crear">CREAR</button>
            <div class="dv-tipo-estado"></div>
        `;
        wrap.appendChild(panel);

        const input = panel.querySelector('.dv-tipo-nombre');
        const crear = panel.querySelector('.dv-tipo-crear');
        const estado = panel.querySelector('.dv-tipo-estado');

        boton.addEventListener('click', function(){{
            panel.classList.toggle('activo');
            if (panel.classList.contains('activo')) input.focus();
        }});

        async function guardar(){{
            const nombre = (input.value || '').trim();
            estado.classList.remove('error');

            if (!nombre){{
                estado.textContent = 'Ingresá un nombre.';
                estado.classList.add('error');
                return;
            }}

            const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
            const datos = new FormData();
            datos.append('nombre', nombre);
            if (csrf) datos.append('csrfmiddlewaretoken', csrf.value);

            crear.disabled = true;
            estado.textContent = 'Creando…';

            try {{
                const respuesta = await fetch(urlCrear, {{
                    method: 'POST',
                    body: datos,
                    credentials: 'same-origin',
                    headers: {{'X-Requested-With': 'XMLHttpRequest'}}
                }});
                const data = await respuesta.json();

                if (!respuesta.ok || !data.ok){{
                    throw new Error(data.mensaje || 'No se pudo crear el tipo.');
                }}

                let opcion = Array.from(select.options).find(function(actual){{
                    return String(actual.value) === String(data.tipo.id);
                }});

                if (!opcion){{
                    opcion = document.createElement('option');
                    opcion.value = data.tipo.id;
                    opcion.textContent = data.tipo.nombre;
                    select.appendChild(opcion);
                }}

                opcion.selected = true;
                select.dispatchEvent(new Event('change', {{bubbles:true}}));
                estado.textContent = data.creado
                    ? 'Tipo creado y seleccionado.'
                    : 'Ese tipo ya existía y quedó seleccionado.';
                input.value = '';
                setTimeout(function(){{panel.classList.remove('activo');}}, 650);
            }} catch (error) {{
                estado.textContent = error.message || 'No se pudo crear el tipo.';
                estado.classList.add('error');
            }} finally {{
                crear.disabled = false;
            }}
        }}

        crear.addEventListener('click', guardar);
        input.addEventListener('keydown', function(evento){{
            if (evento.key === 'Enter'){{
                evento.preventDefault();
                guardar();
            }}
        }});
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""


def _datos_planificacion():
    from pedidos.impresiones_compuestas import obtener_impresiones_por_producto

    datos = []

    for item in obtener_impresiones_por_producto():
        datos.append(
            {
                "producto_id": item["producto"].id,
                "codigo": item["producto"].codigo,
                "nombre": item["producto"].nombre,
                "falta_normal_planificar": int(
                    item["falta_normal_planificar"] or 0
                ),
                "planificadas": int(item["planificadas"] or 0),
                "en_produccion": int(item["en_produccion"] or 0),
                "personalizaciones": [
                    {
                        "detalle_id": personalizacion["detalle_id"],
                        "pedido_codigo": personalizacion["pedido_codigo"],
                        "cantidad": int(personalizacion["cantidad"] or 0),
                        "planificadas": int(
                            personalizacion.get("planificadas") or 0
                        ),
                        "imprimiendo": int(
                            personalizacion.get("imprimiendo") or 0
                        ),
                        "falta_planificar": int(
                            personalizacion.get("falta_planificar") or 0
                        ),
                        "detalle": personalizacion.get("detalle") or "",
                        "color": personalizacion.get("color") or "",
                        "producto_origen": personalizacion.get("producto_origen") or "",
                    }
                    for personalizacion in item["personalizaciones"]
                ],
            }
        )

    return datos


def _script_planificacion(request):
    datos_json = json.dumps(
        _datos_planificacion(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    csrf = json.dumps(get_token(request))
    plan_url = json.dumps(reverse("pedidos:planificar_impresion_producto"))
    tiempo_url = json.dumps(reverse("produccion:tiempo_recomendado"))

    return f"""
<script id="dv-planificar-productos-script">
(function(){{
    const datos = {datos_json};
    const csrf = {csrf};
    const planUrl = {plan_url};
    const tiempoUrl = {tiempo_url};
    const mapa = new Map(datos.map(function(item){{return [item.codigo, item];}}));

    function escapar(texto){{
        const div = document.createElement('div');
        div.textContent = texto || '';
        return div.innerHTML;
    }}

    function ahoraLocal(){{
        const ahora = new Date();
        const offset = ahora.getTimezoneOffset() * 60000;
        return new Date(ahora.getTime() - offset).toISOString().slice(0,16);
    }}

    function formulario(info, maximo, personalizadoId){{
        const ocultoPersonalizado = personalizadoId
            ? `<input type="hidden" name="personalizado_id" value="${{personalizadoId}}">`
            : '';

        return `
            <form method="post" action="${{planUrl}}" class="dv-plan-form" data-producto="${{info.producto_id}}">
                <input type="hidden" name="csrfmiddlewaretoken" value="${{csrf}}">
                <input type="hidden" name="producto" value="${{info.producto_id}}">
                ${{ocultoPersonalizado}}
                <div class="dv-plan-campo">
                    <label>CANTIDAD EN ESTA PLACA</label>
                    <input type="number" name="cantidad" min="1" max="${{maximo}}" placeholder="Cantidad" required>
                </div>
                <div class="dv-plan-campo dv-plan-fecha">
                    <label>DÍA Y HORARIO</label>
                    <input type="datetime-local" name="inicio_impresion" value="${{ahoraLocal()}}" required>
                </div>
                <div class="dv-plan-duracion">
                    <div class="dv-plan-campo">
                        <label>HORAS DE PLACA</label>
                        <input type="number" name="horas" min="0" placeholder="Auto">
                    </div>
                    <div class="dv-plan-campo">
                        <label>MINUTOS</label>
                        <input type="number" name="minutos" min="0" max="59" placeholder="Auto">
                    </div>
                </div>
                <div class="dv-plan-tiempo">Ingresá la cantidad: si existe un tiempo registrado se completa automáticamente.</div>
                <button type="submit" class="dv-plan-enviar">PLANIFICAR PRODUCCIÓN</button>
            </form>
        `;
    }}

    function contenido(info){{
        let html = '<div class="dv-plan-resumen">';
        if (info.planificadas > 0) html += `<span class="dv-plan-chip">◷ PLANIFICADAS ${{info.planificadas}}</span>`;
        if (info.en_produccion > 0) html += `<span class="dv-plan-chip activo">● IMPRIMIENDO ${{info.en_produccion}}</span>`;
        html += '</div>';

        if (info.falta_normal_planificar > 0){{
            html += `
                <details class="dv-plan-details">
                    <summary>＋ PLANIFICAR ESTÁNDAR · quedan ${{info.falta_normal_planificar}}</summary>
                    ${{formulario(info, info.falta_normal_planificar, '')}}
                </details>
            `;
        }}

        const personalizados = info.personalizaciones.filter(function(item){{
            return item.falta_planificar > 0;
        }});

        if (personalizados.length){{
            html += '<div class="dv-personalizados">';
            html += '<div class="dv-personalizados-titulo">⚠ PERSONALIZADOS · NO SE MEZCLAN CON LA PLANIFICACIÓN ESTÁNDAR</div>';

            personalizados.forEach(function(item){{
                const detalle = escapar(item.detalle || 'Sin detalle');
                const color = escapar(item.color || 'Sin color especificado');
                const origen = escapar(item.producto_origen || info.nombre);
                html += `
                    <div class="dv-personalizado">
                        <strong>${{escapar(item.pedido_codigo)}} · ${{origen}} · quedan ${{item.falta_planificar}}</strong>
                        <div class="dv-personalizado-meta">Color: ${{color}} · ${{detalle}}</div>
                        <details class="dv-plan-details">
                            <summary>PLANIFICAR ESTE PERSONALIZADO</summary>
                            ${{formulario(info, item.falta_planificar, item.detalle_id)}}
                        </details>
                    </div>
                `;
            }});

            html += '</div>';
        }}

        if (info.falta_normal_planificar <= 0 && !personalizados.length){{
            html += '<div class="dv-plan-vacio">Toda la necesidad ya está planificada o imprimiéndose.</div>';
        }}

        return html;
    }}

    async function recomendarTiempo(form){{
        const cantidad = form.querySelector('[name="cantidad"]');
        const horas = form.querySelector('[name="horas"]');
        const minutos = form.querySelector('[name="minutos"]');
        const estado = form.querySelector('.dv-plan-tiempo');
        const valor = Number(cantidad.value || 0);

        if (valor <= 0){{
            estado.textContent = 'Ingresá una cantidad para buscar un tiempo registrado.';
            return;
        }}

        estado.textContent = 'Buscando tiempo para esa cantidad…';

        try {{
            const respuesta = await fetch(
                tiempoUrl
                + '?producto=' + encodeURIComponent(form.dataset.producto)
                + '&cantidad=' + encodeURIComponent(valor),
                {{credentials:'same-origin'}}
            );
            const data = await respuesta.json();

            if (data.ok && data.encontrado){{
                horas.value = data.horas || 0;
                minutos.value = data.minutos || 0;
                estado.textContent = '✓ Tiempo completado desde ' + (data.origen === 'HISTORIAL' ? 'el historial de esa cantidad.' : 'el producto.');
            }} else {{
                horas.value = '';
                minutos.value = '';
                estado.textContent = 'Sin historial para esa cantidad: ingresá la duración estimada de la placa.';
            }}
        }} catch (error) {{
            estado.textContent = 'No se pudo consultar el tiempo. Podés ingresarlo manualmente.';
        }}
    }}

    function iniciar(){{
        const tabla = document.querySelector('.tabla-contenedor table');
        if (!tabla || tabla.dataset.dvPlanificacion === '1') return;
        tabla.dataset.dvPlanificacion = '1';

        const filaCabecera = tabla.querySelector('thead tr');
        if (filaCabecera){{
            const th = document.createElement('th');
            th.textContent = 'PLANIFICAR';
            filaCabecera.appendChild(th);
        }}

        tabla.querySelectorAll('tbody tr').forEach(function(fila){{
            const codigo = (fila.querySelector('.codigo')?.textContent || '').trim();
            const info = mapa.get(codigo);
            if (!info) return;

            const td = document.createElement('td');
            td.className = 'dv-planificar-celda';
            td.innerHTML = contenido(info);
            fila.appendChild(td);
        }});

        tabla.addEventListener('input', function(evento){{
            if (!evento.target.matches('.dv-plan-form [name="cantidad"]')) return;
            const form = evento.target.closest('.dv-plan-form');
            clearTimeout(form._dvTiempoTimer);
            form._dvTiempoTimer = setTimeout(function(){{
                recomendarTiempo(form);
            }}, 250);
        }});
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""


class OperacionesUIMiddleware:
    """Reglas operativas de selección y mejoras puntuales de formularios."""

    def __init__(self, get_response):
        self.get_response = get_response

    def process_view(self, request, view_func, view_args, view_kwargs):
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""

        if (
            request.method == "POST"
            and view_name in {"pedidos:nuevo", "pedidos:editar"}
        ):
            ids = _ids_productos_post(request)
            if ids and Producto.objects.filter(
                id__in=ids,
                solo_produccion=True,
            ).exists():
                messages.error(
                    request,
                    (
                        "Las piezas internas no se pueden agregar a un pedido. "
                        "Seleccioná el producto comercial correspondiente."
                    ),
                )

                if view_name == "pedidos:editar":
                    return redirect(
                        "pedidos:editar",
                        pedido_id=view_kwargs.get("pedido_id"),
                    )

                return redirect("pedidos:nuevo")

        return None

    def __call__(self, request):
        response = self.get_response(request)
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""
        content_type = response.get("Content-Type", "")

        if (
            view_name == "pedidos:productos_kit"
            and "application/json" in content_type
            and not getattr(response, "streaming", False)
        ):
            try:
                data = json.loads(response.content.decode(response.charset or "utf-8"))
            except (ValueError, UnicodeDecodeError, AttributeError):
                return response

            ids_piezas = set(_piezas_ids())
            if isinstance(data, dict) and isinstance(data.get("productos"), list):
                data["productos"] = [
                    producto
                    for producto in data["productos"]
                    if producto.get("id") not in ids_piezas
                ]
                encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
                response.content = encoded
                response["Content-Length"] = str(len(encoded))
            return response

        if getattr(response, "streaming", False) or "text/html" not in content_type:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if view_name in {"pedidos:nuevo", "pedidos:editar"}:
            ids_piezas = _piezas_ids()
            if "</head>" in html and "dv-ordenes-productos-style" not in html:
                html = html.replace(
                    "</head>",
                    ORDENES_STYLE + "\n</head>",
                    1,
                )
            if "</body>" in html and "dv-ordenes-productos-script" not in html:
                html = html.replace(
                    "</body>",
                    _script_sin_piezas(ids_piezas) + "\n</body>",
                    1,
                )

        if view_name in {"productos:nuevo", "productos:editar"}:
            if "</head>" in html and "dv-tipos-producto-style" not in html:
                html = html.replace(
                    "</head>",
                    TIPOS_STYLE + "\n</head>",
                    1,
                )
            if "</body>" in html and "dv-tipos-producto-script" not in html:
                html = html.replace(
                    "</body>",
                    _script_nuevo_tipo() + "\n</body>",
                    1,
                )

        if view_name == "pedidos:impresiones_productos":
            if "</head>" in html and "dv-planificar-productos-style" not in html:
                html = html.replace(
                    "</head>",
                    PLAN_STYLE + "\n</head>",
                    1,
                )
            if "</body>" in html and "dv-planificar-productos-script" not in html:
                html = html.replace(
                    "</body>",
                    _script_planificacion(request) + "\n</body>",
                    1,
                )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
