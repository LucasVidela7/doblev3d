(function(){
    const SELECTORES=[
        ".mensajes .mensaje",
        ".messages .message",
        ".messages > li",
        ".mensajes > .dv-impresiones-mensaje"
    ];

    function tipoDe(elemento){
        const clases=(elemento.className||"").toString().toLowerCase();
        if(clases.includes("error") || clases.includes("danger")) return "error";
        if(clases.includes("warning") || clases.includes("warn")) return "warning";
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
        let timer=window.setTimeout(function(){cerrar(toast);},duracion);

        toast.addEventListener("mouseenter",function(){
            window.clearTimeout(timer);
        });
        toast.addEventListener("mouseleave",function(){
            timer=window.setTimeout(function(){cerrar(toast);},1800);
        });

        requestAnimationFrame(function(){
            toast.classList.add("is-visible");
        });
    }

    function convertirMensajes(){
        const vistos=new Set();
        const nodos=[];

        SELECTORES.forEach(function(selector){
            document.querySelectorAll(selector).forEach(function(el){
                if(!vistos.has(el)){
                    vistos.add(el);
                    nodos.push(el);
                }
            });
        });

        nodos.forEach(function(el){
            mostrar(el.textContent,tipoDe(el));
            el.remove();
        });

        document.querySelectorAll(".mensajes,.messages").forEach(function(wrapper){
            if(!wrapper.children.length && !wrapper.textContent.trim()){
                wrapper.remove();
            }
        });
    }

    window.DVToast={
        success:function(texto){mostrar(texto,"success");},
        error:function(texto){mostrar(texto,"error");},
        warning:function(texto){mostrar(texto,"warning");},
        info:function(texto){mostrar(texto,"info");}
    };

    if(document.readyState==="loading"){
        document.addEventListener("DOMContentLoaded",convertirMensajes);
    }else{
        convertirMensajes();
    }
})();
