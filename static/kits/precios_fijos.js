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

    function renderizarLibre(data){
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
                        La categoría tiene ${data.productos_categoria} productos comerciales. El kit usa el costo de filamento para cantidad y compara el comportamiento promedio con el producto más exigente.
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

        datos.append("tipo_producto", tipoId);
        datos.append("cantidad", cantidad);

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
