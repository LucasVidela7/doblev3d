(function(){
    const SELECTORES=[
        "[data-dv-toast]",
        ".mensajes .mensaje",
        ".messages .message",
        ".messages > li",
        ".message.success",
        ".message.error",
        ".message.warning",
        ".message.info",
        ".mensaje.success",
        ".mensaje.error",
        ".mensaje.warning",
        ".mensaje.info",
        ".alert.alert-success",
        ".alert.alert-danger",
        ".alert.alert-error",
        ".alert.alert-warning",
        ".alert.alert-info",
        ".dv-impresiones-mensaje.success",
        ".dv-impresiones-mensaje.error",
        ".dv-impresiones-mensaje.warning",
        ".dv-impresiones-mensaje.info"
    ];

    function tipoDe(elemento){
        const forzado=(
            elemento.dataset
            && elemento.dataset.dvToastType
            || ""
        ).toLowerCase();

        if(["success","error","warning","info"].includes(forzado)){
            return forzado;
        }

        const clases=(elemento.className||"").toString().toLowerCase();

        if(
            clases.includes("error")
            || clases.includes("danger")
            || clases.includes("alert-danger")
        ) return "error";

        if(
            clases.includes("warning")
            || clases.includes("warn")
        ) return "warning";

        if(clases.includes("success")) return "success";

        return "info";
    }

    function icono(tipo){
        if(tipo==="success") return "✓";
        if(tipo==="error") return "!";
        if(tipo==="warning") return "!";
        return "i";
    }

    function titulo(tipo){
        if(tipo==="success") return "Listo";
        if(tipo==="error") return "Error";
        if(tipo==="warning") return "Atención";
        return "Información";
    }

    function asegurarContenedor(){
        let contenedor=document.getElementById("dvToastStack");
        if(contenedor) return contenedor;

        contenedor=document.createElement("div");
        contenedor.id="dvToastStack";
        contenedor.className="dv-toast-stack";
        contenedor.setAttribute("aria-live","polite");
        contenedor.setAttribute("aria-relevant","additions");
        document.body.appendChild(contenedor);
        return contenedor;
    }

    function cerrar(toast){
        if(!toast || toast.classList.contains("is-leaving")) return;
        toast.classList.add("is-leaving");
        window.setTimeout(function(){
            toast.remove();
        },180);
    }

    function mostrar(texto,tipo){
        texto=(texto||"").replace(/\s+/g," ").trim();
        if(!texto) return;

        const contenedor=asegurarContenedor();
        const toast=document.createElement("div");
        toast.className="dv-toast dv-toast--"+tipo;
        toast.setAttribute("role",tipo==="error"?"alert":"status");

        const simbolo=document.createElement("span");
        simbolo.className="dv-toast__icon";
        simbolo.setAttribute("aria-hidden","true");
        simbolo.textContent=icono(tipo);

        const cuerpo=document.createElement("div");
        cuerpo.className="dv-toast__body";

        const encabezado=document.createElement("div");
        encabezado.className="dv-toast__title";
        encabezado.textContent=titulo(tipo);

        const mensaje=document.createElement("div");
        mensaje.className="dv-toast__message";
        mensaje.textContent=texto;

        const boton=document.createElement("button");
        boton.type="button";
        boton.className="dv-toast__close";
        boton.setAttribute("aria-label","Cerrar aviso");
        boton.textContent="×";
        boton.addEventListener("click",function(){
            cerrar(toast);
        });

        cuerpo.appendChild(encabezado);
        cuerpo.appendChild(mensaje);
        toast.appendChild(simbolo);
        toast.appendChild(cuerpo);
        toast.appendChild(boton);
        contenedor.appendChild(toast);

        const duracion=tipo==="error"||tipo==="warning"?6500:4500;
        let timer=window.setTimeout(function(){
            cerrar(toast);
        },duracion);

        toast.addEventListener("mouseenter",function(){
            window.clearTimeout(timer);
        });

        toast.addEventListener("mouseleave",function(){
            timer=window.setTimeout(function(){
                cerrar(toast);
            },1800);
        });

        requestAnimationFrame(function(){
            toast.classList.add("is-visible");
        });
    }

    function candidatosEn(root){
        const encontrados=[];

        if(root && root.nodeType===1){
            SELECTORES.forEach(function(selector){
                if(root.matches && root.matches(selector)){
                    encontrados.push(root);
                }

                if(root.querySelectorAll){
                    root.querySelectorAll(selector).forEach(function(el){
                        encontrados.push(el);
                    });
                }
            });
        }

        return encontrados;
    }

    function limpiarWrappers(){
        document.querySelectorAll(
            ".mensajes,.messages"
        ).forEach(function(wrapper){
            if(
                !wrapper.children.length
                && !wrapper.textContent.trim()
            ){
                wrapper.remove();
            }
        });
    }

    function convertir(root){
        const vistos=new Set();

        candidatosEn(root||document.body).forEach(function(el){
            if(
                vistos.has(el)
                || el.dataset.dvToastConverted==="1"
                || el.closest("#dvToastStack")
            ){
                return;
            }

            vistos.add(el);
            el.dataset.dvToastConverted="1";
            mostrar(el.textContent,tipoDe(el));
            el.remove();
        });

        limpiarWrappers();
    }

    function observar(){
        if(!window.MutationObserver || !document.body) return;

        const observer=new MutationObserver(function(mutations){
            mutations.forEach(function(mutation){
                mutation.addedNodes.forEach(function(node){
                    if(node.nodeType===1){
                        convertir(node);
                    }
                });
            });
        });

        observer.observe(document.body,{
            childList:true,
            subtree:true
        });
    }

    function iniciar(){
        convertir(document.body);
        observar();
    }

    window.DVToast={
        success:function(texto){mostrar(texto,"success");},
        error:function(texto){mostrar(texto,"error");},
        warning:function(texto){mostrar(texto,"warning");},
        info:function(texto){mostrar(texto,"info");}
    };

    if(document.readyState==="loading"){
        document.addEventListener("DOMContentLoaded",iniciar);
    }else{
        iniciar();
    }
})();
