(function(){
    const script = document.currentScript;
    const endpoint = script?.dataset.recomendacionUrl || "";

    if (!endpoint) return;

    const actualizarOriginal = window.actualizarRecomendacion;
    let panel = null;
    let contenedor = null;
    let timer = null;

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

    function descripcionEscenario(clave){
        if (clave === "agresivo") {
            return "Menor precio de los tres escenarios, manteniendo el piso y la lógica de descuentos de la calculadora.";
        }
        if (clave === "conservador") {
            return "Mayor margen para absorber variaciones de costos y conservar más rentabilidad.";
        }
        return "Equilibrio sugerido por la calculadora según margen y cantidad de cada producto.";
    }

    function tituloEscenario(clave){
        return {
            agresivo:"AGRESIVO",
            recomendado:"RECOMENDADO",
            conservador:"CONSERVADOR"
        }[clave] || clave.toUpperCase();
    }

    function renderizar(data){
        if (!contenedor) return;

        const precioActual = Number(
            document.getElementById("precio_kit")?.value || 0
        );
        const agresivo = Number(data.escenarios.agresivo.precio || 0);
        const recomendado = Number(data.escenarios.recomendado.precio || 0);

        let estadoPrecio = "Sin precio ingresado";
        let alerta = false;

        if (precioActual > 0 && precioActual < agresivo) {
            estadoPrecio = "Precio actual por debajo del escenario agresivo";
            alerta = true;
        } else if (precioActual >= agresivo && precioActual < recomendado) {
            estadoPrecio = "Precio actual entre agresivo y recomendado";
            alerta = true;
        } else if (precioActual >= recomendado) {
            estadoPrecio = "Precio actual dentro o por encima del recomendado";
        }

        const tarjetas = [
            "agresivo",
            "recomendado",
            "conservador"
        ].map(function(clave){
            const escenario = data.escenarios[clave];
            return `
                <div class="dv-kit-escenario ${clave}">
                    <div class="dv-kit-escenario-nombre">${tituloEscenario(clave)}</div>
                    <div class="dv-kit-escenario-precio">${dinero(escenario.precio)}</div>
                    <div class="dv-kit-escenario-margen">Margen real ${porcentaje(escenario.margen_real)}</div>
                    <div class="dv-kit-escenario-ayuda">${descripcionEscenario(clave)}</div>
                    <button
                        type="button"
                        class="dv-kit-usar-precio"
                        data-precio="${escenario.precio}"
                    >
                        USAR ESTE PRECIO
                    </button>
                </div>
            `;
        }).join("");

        contenedor.innerHTML = `
            <div class="dv-kit-escenarios-cabecera">
                <div>
                    <div class="dv-kit-escenarios-etiqueta">PRECIOS SEGÚN CALCULADORA</div>
                    <div class="dv-kit-escenarios-titulo">Composición fija</div>
                    <div class="dv-kit-escenarios-detalle">
                        Costo productivo total: ${dinero(data.costo_total)} · piso de la calculadora: ${porcentaje(data.margen_piso)}.
                        Cada producto conserva su propio margen configurado y el descuento correspondiente a su cantidad dentro del kit.
                    </div>
                </div>
                <div class="dv-kit-precio-actual${alerta ? " alerta" : ""}">
                    ${estadoPrecio}
                </div>
            </div>
            <div class="dv-kit-escenarios-grid">${tarjetas}</div>
        `;
    }

    async function consultar(){
        if (!panel || !contenedor) return;

        if (modalidadActual() !== "FIJO") {
            panel.classList.remove("dv-kit-fijo-activo");
            return;
        }

        panel.classList.add("dv-kit-fijo-activo");

        const componentes = componentesActuales();
        if (!componentes.length) {
            mostrarEstado(
                "Agregá productos y cantidades a la composición fija para ver los tres escenarios de precio.",
                false
            );
            return;
        }

        mostrarEstado("Calculando con la calculadora de precios…", false);

        const datos = new FormData();
        const csrf = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );
        if (csrf) datos.append("csrfmiddlewaretoken", csrf.value);

        componentes.forEach(function(item){
            datos.append("producto_id", item.productoId);
            datos.append("cantidad", item.cantidad);
        });

        try {
            const respuesta = await fetch(endpoint, {
                method:"POST",
                body:datos,
                credentials:"same-origin",
                headers:{"X-Requested-With":"XMLHttpRequest"}
            });
            const data = await respuesta.json();

            if (!respuesta.ok || !data.ok) {
                throw new Error(
                    data.mensaje || "No se pudo calcular la recomendación."
                );
            }

            renderizar(data);
        } catch (error) {
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
        if (typeof actualizarOriginal === "function") {
            actualizarOriginal();
        }

        if (modalidadActual() === "FIJO") {
            programarConsulta();
        } else if (panel) {
            panel.classList.remove("dv-kit-fijo-activo");
        }
    };

    function iniciar(){
        panel = document.getElementById("recomendacion_precio");
        if (!panel || panel.dataset.dvCalculadoraKit === "1") return;

        panel.dataset.dvCalculadoraKit = "1";

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
