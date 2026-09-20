(function(){
    const script = document.currentScript;
    const endpointFijo = script?.dataset.recomendacionFijaUrl || "";
    const endpointLibre = script?.dataset.recomendacionLibreUrl || "";

    if (!endpointFijo || !endpointLibre) return;

    let panel = null;
    let contenedor = null;
    let timer = null;
    let secuencia = 0;

    function modalidadActual(){
        return document.querySelector(
            '[name="modalidad"]:checked'
        )?.value || "LIBRE_CATEGORIA";
    }

    function dinero(valor){
        return new Intl.NumberFormat(
            "es-AR",
            {
                style:"currency",
                currency:"ARS",
                maximumFractionDigits:0
            }
        ).format(Number(valor || 0));
    }

    function porcentaje(valor){
        const numero = Number(valor);
        if (!Number.isFinite(numero)) return "—";
        return `${numero.toFixed(1).replace(".", ",")}%`;
    }

    function componentesActuales(){
        const componentes = [];

        document.querySelectorAll(".componente").forEach(function(fila){
            const productoId = fila.querySelector(
                '[name="componente_producto"]'
            )?.value || "";
            const cantidad = Number(
                fila.querySelector(
                    '[name="componente_cantidad"]'
                )?.value || 0
            );

            if (productoId && cantidad > 0) {
                componentes.push({
                    productoId: productoId,
                    cantidad: cantidad
                });
            }
        });

        return componentes;
    }

    function mostrarEstado(texto, error){
        if (!contenedor) return;
        contenedor.innerHTML = `
            <div class="dv-kit-escenarios-estado${error ? " error" : ""}">
                ${texto}
            </div>
        `;
    }

    function tituloEscenario(clave){
        return {
            agresivo:"AGRESIVO",
            recomendado:"RECOMENDADO",
            conservador:"CONSERVADOR"
        }[clave] || clave.toUpperCase();
    }

    function descripcionEscenario(clave, tipo){
        if (tipo === "LIBRE_CATEGORIA") {
            if (clave === "agresivo") {
                return "Toma como referencia el promedio de la categoría con el escenario agresivo de la calculadora. Es el precio más competitivo.";
            }
            if (clave === "conservador") {
                return "Usa el escenario conservador del producto más exigente de la categoría. Es el que más protege la rentabilidad.";
            }
            return "Parte del promedio recomendado, pero nunca queda por debajo del escenario agresivo del producto más exigente de la categoría.";
        }

        if (clave === "agresivo") {
            return "Menor precio de los tres escenarios, manteniendo el piso y la lógica de descuentos de la calculadora.";
        }
        if (clave === "conservador") {
            return "Mayor margen para absorber variaciones de costos y conservar más rentabilidad.";
        }
        return "Equilibrio sugerido por la calculadora según margen y cantidad de cada producto.";
    }

    function chipFilamento(data){
        const filamento = data.filamento;
        if (!filamento || Number(filamento.precio_kg || 0) <= 0) return "";

        const etiqueta = filamento.economico
            ? "Filamento para cantidad"
            : "Filamento estándar";

        return `
            <span class="dv-kit-costo-chip">
                ${etiqueta} ${dinero(filamento.precio_kg)}/kg
            </span>
        `;
    }

    function estadoPrecioActual(data){
        const precioActual = Number(
            document.getElementById("precio_kit")?.value || 0
        );
        const agresivo = Number(data.escenarios.agresivo.precio || 0);
        const recomendado = Number(data.escenarios.recomendado.precio || 0);

        if (!precioActual) {
            return {
                texto:"Sin precio ingresado",
                alerta:false
            };
        }

        if (precioActual < agresivo) {
            return {
                texto:"Precio actual por debajo del escenario agresivo",
                alerta:true
            };
        }

        if (precioActual < recomendado) {
            return {
                texto:"Precio actual entre agresivo y recomendado",
                alerta:true
            };
        }

        return {
            texto:"Precio actual dentro o por encima del recomendado",
            alerta:false
        };
    }

    function tarjetaEscenario(data, clave){
        const escenario = data.escenarios[clave];
        const libre = data.tipo === "LIBRE_CATEGORIA";

        const margen = libre
            ? `Margen promedio ${porcentaje(escenario.margen_promedio)}`
            : `Margen real ${porcentaje(escenario.margen_real)}`;

        const riesgo = libre
            ? `<div class="dv-kit-escenario-riesgo">Peor caso ${porcentaje(escenario.margen_peor_caso)}</div>`
            : "";

        return `
            <div class="dv-kit-escenario ${clave}">
                <div class="dv-kit-escenario-nombre">${tituloEscenario(clave)}</div>
                <div class="dv-kit-escenario-precio">${dinero(escenario.precio)}</div>
                <div class="dv-kit-escenario-margen">${margen}</div>
                ${riesgo}
                <div class="dv-kit-escenario-ayuda">${descripcionEscenario(clave, data.tipo)}</div>
                <button
                    type="button"
                    class="dv-kit-usar-precio"
                    data-precio="${escenario.precio}"
                >
                    USAR ESTE PRECIO
                </button>
            </div>
        `;
    }

    function renderizarFijo(data){
        const estado = estadoPrecioActual(data);
        const tarjetas = [
            "agresivo",
            "recomendado",
            "conservador"
        ].map(function(clave){
            return tarjetaEscenario(data, clave);
        }).join("");

        contenedor.innerHTML = `
            <div class="dv-kit-escenarios-cabecera">
                <div>
                    <div class="dv-kit-escenarios-etiqueta">PRECIOS SEGÚN CALCULADORA</div>
                    <div class="dv-kit-escenarios-titulo">Composición fija</div>
                    <div class="dv-kit-escenarios-detalle">
                        El kit usa el costo de filamento para cantidad cuando está configurado. Los productos individuales siguen conservando el costo estándar.
                    </div>
                    <div class="dv-kit-costos">
                        <span class="dv-kit-costo-chip">Costo productivo ${dinero(data.costo_total)}</span>
                        ${chipFilamento(data)}
                        <span class="dv-kit-costo-chip">Piso calculadora ${porcentaje(data.margen_piso)}</span>
                    </div>
                </div>
                <div class="dv-kit-precio-actual${estado.alerta ? " alerta" : ""}">
                    ${estado.texto}
                </div>
            </div>
            <div class="dv-kit-escenarios-grid">${tarjetas}</div>
        `;
    }

    function opcionesRentabilidadHtml(data){
        const info = data.opciones_rentabilidad;
        if (!info || !info.disponible) return "";

        const opciones = Array.isArray(info.opciones)
            ? info.opciones
            : [];

        if (!info.proteger_rentabilidad) {
            const potenciales = opciones.filter(function(item){
                return item.requiere_extra;
            }).length;

            return `
                <div class="dv-kit-opciones-rentabilidad desactivada">
                    <div class="dv-kit-opciones-titulo">
                        PROTECCIÓN DE RENTABILIDAD DESACTIVADA
                    </div>
                    <div class="dv-kit-opciones-ayuda">
                        Todos los productos de la categoría quedan incluidos al precio base.
                        ${potenciales > 0
                            ? potenciales + " opción" + (potenciales === 1 ? "" : "es")
                                + " necesitaría" + (potenciales === 1 ? "" : "n")
                                + " extra si activaras la protección."
                            : "Ninguna opción necesita extra con el precio actual."}
                    </div>
                </div>
            `;
        }

        const incluidos = opciones.filter(function(item){
            return item.incluido;
        });
        const premium = opciones.filter(function(item){
            return !item.incluido;
        });

        const chipsIncluidos = incluidos.map(function(item){
            return `<span class="dv-kit-opcion-chip incluida">${item.nombre}</span>`;
        }).join("");

        const chipsPremium = premium.map(function(item){
            return `
                <span class="dv-kit-opcion-chip premium">
                    ${item.nombre}
                    <strong>+${dinero(item.extra)}</strong>
                </span>
            `;
        }).join("");

        return `
            <div class="dv-kit-opciones-rentabilidad">
                <div class="dv-kit-opciones-resumen">
                    <div>
                        <div class="dv-kit-opciones-titulo">OPCIONES INCLUIDAS</div>
                        <div class="dv-kit-opciones-numero">${incluidos.length}</div>
                    </div>
                    <div>
                        <div class="dv-kit-opciones-titulo">CON ADICIONAL</div>
                        <div class="dv-kit-opciones-numero">${premium.length}</div>
                    </div>
                    <div>
                        <div class="dv-kit-opciones-titulo">BASE POR LUGAR</div>
                        <div class="dv-kit-opciones-numero">${dinero(info.precio_base_por_lugar)}</div>
                    </div>
                </div>

                <div class="dv-kit-opciones-grupo">
                    <div class="dv-kit-opciones-subtitulo">Incluidas en el precio del kit</div>
                    <div class="dv-kit-opciones-chips">
                        ${chipsIncluidos || '<span class="dv-kit-opciones-vacio">No hay opciones incluidas con este precio.</span>'}
                    </div>
                </div>

                ${premium.length ? `
                    <div class="dv-kit-opciones-grupo">
                        <div class="dv-kit-opciones-subtitulo">Opciones con adicional</div>
                        <div class="dv-kit-opciones-chips">
                            ${chipsPremium}
                        </div>
                    </div>
                ` : ""}
            </div>
        `;
    }

    function renderizarLibre(data){
        const info = data.opciones_rentabilidad || {};
        const protegido = !!info.proteger_rentabilidad;
        const sinIncluidos = !!data.sin_opciones_incluidas;

        if (protegido) {
            const estadoTexto = sinIncluidos
                ? "Sin opciones incluidas con el precio base actual"
                : "Precio base protegido";

            contenedor.innerHTML = `
                <div class="dv-kit-escenarios-cabecera">
                    <div>
                        <div class="dv-kit-escenarios-etiqueta">PRECIO BASE DEL KIT</div>
                        <div class="dv-kit-escenarios-titulo">Libre por categoría · ${data.categoria}</div>
                        <div class="dv-kit-escenarios-detalle">
                            La protección está activa. El precio base define qué productos quedan incluidos;
                            las opciones más exigentes se ofrecen con un adicional propio.
                            Por eso no se muestra un único precio recomendado para todo el kit.
                        </div>
                        <div class="dv-kit-costos">
                            <span class="dv-kit-costo-chip">
                                ${data.productos_referencia} opciones incluidas
                            </span>
                            ${sinIncluidos ? "" : `
                                <span class="dv-kit-costo-chip">
                                    Costo promedio incluidos ${dinero(data.costo_promedio)}
                                </span>
                                <span class="dv-kit-costo-chip riesgo">
                                    Mayor costo incluido ${dinero(data.costo_peor_caso)}
                                </span>
                                ${chipFilamento(data)}
                            `}
                        </div>
                    </div>
                    <div class="dv-kit-precio-actual ${sinIncluidos ? "critico" : "protegido"}">
                        ${estadoTexto}
                    </div>
                </div>

                ${opcionesRentabilidadHtml(data)}

                <div class="dv-kit-base-protegida ${sinIncluidos ? "alerta" : ""}">
                    ${sinIncluidos
                        ? `
                            <strong>Revisá el precio base.</strong>
                            Con el valor actual todos los productos necesitan adicional.
                            Subí el precio o reducí la cantidad de productos del kit para que exista al menos una opción incluida.
                        `
                        : `
                            <strong>El precio base se administra por cobertura, no por una recomendación única.</strong>
                            Mientras una opción permanezca incluida, cumple el escenario mínimo definido por la protección.
                            Los productos con adicional completan su rentabilidad mediante el importe mostrado arriba.
                        `
                    }
                </div>
            `;
            return;
        }

        const estado = estadoPrecioActual(data);
        const tarjetas = [
            "agresivo",
            "recomendado",
            "conservador"
        ].map(function(clave){
            return tarjetaEscenario(data, clave);
        }).join("");

        contenedor.innerHTML = `
            <div class="dv-kit-escenarios-cabecera">
                <div>
                    <div class="dv-kit-escenarios-etiqueta">PRECIOS SEGÚN CALCULADORA</div>
                    <div class="dv-kit-escenarios-titulo">Libre por categoría · ${data.categoria}</div>
                    <div class="dv-kit-escenarios-detalle">
                        La protección está desactivada. Todos los productos de la categoría comparten el mismo precio base,
                        por eso la recomendación contempla promedio y peor caso de toda la categoría.
                    </div>
                    <div class="dv-kit-costos">
                        <span class="dv-kit-costo-chip">Costo promedio ${dinero(data.costo_promedio)}</span>
                        <span class="dv-kit-costo-chip riesgo">Peor costo ${dinero(data.costo_peor_caso)}</span>
                        ${chipFilamento(data)}
                        <span class="dv-kit-costo-chip">Piso calculadora ${porcentaje(data.margen_piso)}</span>
                    </div>
                </div>
                <div class="dv-kit-precio-actual${estado.alerta ? " alerta" : ""}">
                    ${estado.texto}
                </div>
            </div>
            ${opcionesRentabilidadHtml(data)}
            <div class="dv-kit-escenarios-grid">${tarjetas}</div>
        `;
    }

    function renderizar(data){
        if (!contenedor) return;

        if (data.tipo === "LIBRE_CATEGORIA") {
            renderizarLibre(data);
        } else {
            renderizarFijo(data);
        }
    }

    function agregarCsrf(datos){
        const csrf = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );
        if (csrf) datos.append("csrfmiddlewaretoken", csrf.value);
    }

    function prepararConsulta(){
        const modalidad = modalidadActual();
        const datos = new FormData();
        agregarCsrf(datos);

        if (modalidad === "FIJO") {
            const componentes = componentesActuales();
            if (!componentes.length) {
                return {
                    error:"Agregá productos y cantidades a la composición fija para ver los tres escenarios de precio."
                };
            }

            componentes.forEach(function(item){
                datos.append("producto_id", item.productoId);
                datos.append("cantidad", item.cantidad);
            });

            return {
                endpoint:endpointFijo,
                datos:datos
            };
        }

        const tipoId = document.getElementById("tipo_producto")?.value || "";
        const cantidad = Number(
            document.getElementById("cantidad_productos")?.value || 0
        );

        if (!tipoId || cantidad <= 0) {
            return {
                error:"Elegí una categoría y la cantidad del kit para calcular Agresivo, Recomendado y Conservador."
            };
        }

        const precio = Number(
            document.getElementById("precio_kit")?.value || 0
        );
        const proteger = !!document.getElementById(
            "proteger_rentabilidad_libre"
        )?.checked;

        datos.append("tipo_producto", tipoId);
        datos.append("cantidad", cantidad);
        datos.append("precio", precio);
        datos.append(
            "proteger_rentabilidad",
            proteger ? "1" : "0"
        );

        return {
            endpoint:endpointLibre,
            datos:datos
        };
    }

    async function consultar(){
        if (!panel || !contenedor) return;

        panel.classList.add("dv-kit-calculadora-activo");

        const consulta = prepararConsulta();
        if (consulta.error) {
            mostrarEstado(consulta.error, false);
            return;
        }

        const miSecuencia = ++secuencia;
        mostrarEstado("Calculando con la calculadora de precios…", false);

        try {
            const respuesta = await fetch(consulta.endpoint, {
                method:"POST",
                body:consulta.datos,
                credentials:"same-origin",
                headers:{"X-Requested-With":"XMLHttpRequest"}
            });
            const data = await respuesta.json();

            if (miSecuencia !== secuencia) return;

            if (!respuesta.ok || !data.ok) {
                throw new Error(
                    data.mensaje || "No se pudo calcular la recomendación."
                );
            }

            renderizar(data);
        } catch (error) {
            if (miSecuencia !== secuencia) return;
            mostrarEstado(
                error.message || "No se pudo calcular la recomendación.",
                true
            );
        }
    }

    function programarConsulta(){
        clearTimeout(timer);
        timer = setTimeout(consultar, 180);
    }

    window.actualizarRecomendacion = function(){
        programarConsulta();
    };

    function iniciar(){
        panel = document.getElementById("recomendacion_precio");
        if (!panel || panel.dataset.dvCalculadoraKit === "1") return;

        panel.dataset.dvCalculadoraKit = "1";
        panel.classList.add("dv-kit-calculadora-activo");

        Array.from(panel.children).forEach(function(hijo){
            if (hijo.hasAttribute("data-dv-kit-persistente")) {
                return;
            }
            hijo.classList.add("dv-kit-original");
        });

        contenedor = document.createElement("div");
        contenedor.className = "dv-kit-escenarios";
        panel.appendChild(contenedor);

        contenedor.addEventListener("click", function(evento){
            const boton = evento.target.closest(".dv-kit-usar-precio");
            if (!boton) return;

            const precio = boton.dataset.precio;
            const input = document.getElementById("precio_kit");
            if (!input || !precio) return;

            input.value = precio;
            input.dispatchEvent(
                new Event("input", {bubbles:true})
            );
        });

        window.actualizarRecomendacion();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
