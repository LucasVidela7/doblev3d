(function(){
    const STORAGE_KEY="dv-theme";
    const root=document.documentElement;

    function leerTema(){
        try{
            const saved=localStorage.getItem(STORAGE_KEY);
            if(saved==="dark" || saved==="light"){
                return saved;
            }
        }catch(error){}
        return "light";
    }

    function guardarTema(theme){
        try{
            localStorage.setItem(STORAGE_KEY,theme);
        }catch(error){}
    }

    function aplicarTema(theme,guardar){
        const normalizado=theme==="dark"?"dark":"light";
        root.setAttribute("data-dv-theme",normalizado);

        const check=document.getElementById("dvThemeToggle");
        if(check){
            check.checked=normalizado==="dark";
            check.setAttribute(
                "aria-label",
                normalizado==="dark"
                    ?"Cambiar a modo claro"
                    :"Cambiar a modo oscuro"
            );
        }

        const texto=document.getElementById("dvThemeText");
        if(texto){
            texto.textContent=normalizado==="dark"?"OSCURO":"CLARO";
        }

        if(guardar){
            guardarTema(normalizado);
        }
    }

    function mostrarLoader(){
        const loader=document.getElementById("dvPageLoader");
        if(!loader) return;
        loader.classList.add("is-visible");
        loader.setAttribute("aria-hidden","false");
    }

    function ocultarLoader(){
        const loader=document.getElementById("dvPageLoader");
        if(!loader) return;
        loader.classList.remove("is-visible");
        loader.setAttribute("aria-hidden","true");
    }

    function esNavegacionInterna(link){
        if(!link || !link.href) return false;
        if(link.target && link.target.toLowerCase()==="_blank") return false;
        if(link.hasAttribute("download")) return false;

        const raw=link.getAttribute("href")||"";
        if(!raw || raw.startsWith("#")) return false;
        if(/^(mailto:|tel:|javascript:)/i.test(raw)) return false;

        let destino;
        try{
            destino=new URL(link.href,window.location.href);
        }catch(error){
            return false;
        }

        if(destino.origin!==window.location.origin) return false;

        const mismoDocumento=
            destino.pathname===window.location.pathname &&
            destino.search===window.location.search &&
            destino.hash;

        return !mismoDocumento;
    }


    function textoAccion(elemento){
        return (elemento.textContent||"")
            .replace(/\s+/g," ")
            .trim()
            .toUpperCase();
    }

    function accionReal(elemento){
        if(!elemento) return null;
        if(elemento.matches("a,button,summary")) return elemento;
        return elemento.querySelector("a,button,summary");
    }

    function esAccionPrincipal(elemento){
        const accion=accionReal(elemento);
        if(!accion) return false;

        const clases=[
            elemento.className||"",
            accion.className||""
        ].join(" ").toLowerCase();

        const texto=textoAccion(accion);

        return (
            elemento.hasAttribute("data-dv-primary")
            || accion.hasAttribute("data-dv-primary")
            || /(?:^|\s)(?:primary|principal|dark|boton-principal|btn-principal|accion-principal|boton-guardar|guardar|approve|convert|btn-entregar)(?:\s|$)/.test(clases)
            || /^(?:\+|＋|✓)?\s*(?:NUEVO|NUEVA|CREAR|GUARDAR|APROBAR|CONVERTIR|PLANIFICAR|SUBIR|CALCULAR|AGREGAR|ENTREGAR|REGISTRAR)/.test(texto)
            || /^EDITAR(?:\s|$)/.test(texto)
        );
    }

    function ancestroCabecera(contenedor){
        let nodo=contenedor.parentElement;
        let pasos=0;
        const selectorCabecera=[
            "header",
            ".header",
            ".head",
            ".h",
            ".encabezado",
            ".cabecera",
            ".cfg-head"
        ].join(",");

        while(nodo && pasos<4){
            if(
                nodo.matches(selectorCabecera)
                && nodo.querySelector("h1")
            ){
                return nodo;
            }
            nodo=nodo.parentElement;
            pasos+=1;
        }
        return null;
    }

    function crearOverflow(acciones){
        const details=document.createElement("details");
        details.className="dv-page-overflow";

        const summary=document.createElement("summary");
        summary.setAttribute("aria-label","Más acciones");
        summary.textContent="⋯";

        const menu=document.createElement("div");
        menu.className="dv-page-overflow__menu";

        details.append(summary,menu);

        acciones.forEach(function(item){
            item.classList.remove(
                "dv-page-action-secondary",
                "dv-page-action-primary"
            );
            item.classList.add("dv-page-overflow__item");
            menu.appendChild(item);
        });

        return details;
    }

    function normalizarCabecerasGestion(){
        const selector=[
            ".acciones",
            ".actions",
            ".header-actions",
            ".acciones-encabezado",
            ".acciones-head",
            ".acciones-cabecera",
            ".cabecera-acciones",
            ".head-actions",
            ".top-actions",
            ".toolbar-actions",
            ".h > .a",
            ".header > .a",
            ".head > .a"
        ].join(",");

        document.querySelectorAll(selector).forEach(function(acciones){
            if(
                acciones.closest(".modal,.panel,.card,.item,.pedido,.printer")
                && !acciones.parentElement.querySelector("h1")
            ){
                return;
            }

            const cabecera=ancestroCabecera(acciones);
            if(!cabecera) return;

            const titulo=cabecera.querySelector("h1");
            if(!titulo) return;

            cabecera.classList.add("dv-page-head");
            acciones.classList.add("dv-page-actions");

            const hijos=Array.from(acciones.children).filter(function(item){
                return (
                    item.matches("a,button,form,details")
                    && item.offsetParent!==null
                );
            });

            if(!hijos.length){
                acciones.classList.add("is-empty");
                return;
            }

            let overflowExistente=hijos.find(function(item){
                return item.matches("details");
            })||null;

            let normales=hijos.filter(function(item){
                return item!==overflowExistente;
            });

            let principal=normales.find(esAccionPrincipal)||null;

            normales.forEach(function(item){
                item.classList.remove(
                    "dv-page-action-secondary",
                    "dv-page-action-primary"
                );
                item.classList.add(
                    item===principal
                        ?"dv-page-action-primary"
                        :"dv-page-action-secondary"
                );
            });

            if(principal){
                acciones.appendChild(principal);
            }

            normales=Array.from(
                acciones.querySelectorAll(
                    ":scope > .dv-page-action-secondary"
                )
            );

            const esMobile=window.matchMedia("(max-width:720px)").matches;
            const limiteSecundarias=esMobile
                ? (principal ? 1 : 2)
                : 2;
            if(normales.length>limiteSecundarias){
                const extras=normales.slice(limiteSecundarias);
                if(overflowExistente){
                    const menu=
                        overflowExistente.querySelector(
                            ".more-popover,.dv-page-overflow__menu"
                        )
                        || overflowExistente;
                    extras.forEach(function(item){
                        item.classList.remove("dv-page-action-secondary");
                        item.classList.add("dv-page-overflow__item");
                        menu.appendChild(item);
                    });
                }else{
                    overflowExistente=crearOverflow(extras);
                }
            }

            if(overflowExistente){
                overflowExistente.classList.add("dv-page-overflow");
                acciones.appendChild(overflowExistente);
            }
        });

        document.querySelectorAll(
            "header,.header,.head,.h,.encabezado,.cabecera,.cfg-head"
        ).forEach(function(cabecera){
            if(
                !cabecera.querySelector("h1")
                || cabecera.querySelector(":scope > .dv-page-actions")
                || cabecera.querySelector(":scope > .acciones")
                || cabecera.querySelector(":scope > .actions")
                || cabecera.querySelector(":scope > .header-actions")
                || cabecera.querySelector(":scope > .acciones-encabezado")
                || cabecera.querySelector(":scope > .acciones-head")
            ){
                return;
            }

            const directas=Array.from(cabecera.children).filter(function(item){
                return item.matches("a,button,form,details");
            });

            if(!directas.length) return;

            const barra=document.createElement("div");
            barra.className="dv-page-actions";
            directas.forEach(function(item){
                barra.appendChild(item);
            });
            cabecera.appendChild(barra);
            cabecera.classList.add("dv-page-head");

            const principal=directas.find(esAccionPrincipal)||null;
            directas.forEach(function(item){
                item.classList.add(
                    item===principal
                        ?"dv-page-action-primary"
                        :"dv-page-action-secondary"
                );
            });
            if(principal){
                barra.appendChild(principal);
            }
        });

        document.addEventListener("click",function(event){
            document.querySelectorAll(
                ".dv-page-overflow[open],.more-menu[open]"
            ).forEach(function(menu){
                if(!menu.contains(event.target)){
                    menu.removeAttribute("open");
                }
            });
        });
    }

    function conectar(){
        const check=document.getElementById("dvThemeToggle");
        aplicarTema(leerTema(),false);
        normalizarCabecerasGestion();

        if(check){
            check.addEventListener("change",function(){
                aplicarTema(
                    check.checked?"dark":"light",
                    true
                );
            });
        }

        document.addEventListener("click",function(event){
            if(event.defaultPrevented) return;
            if(event.button!==0) return;
            if(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

            const link=event.target.closest("a[href]");
            if(esNavegacionInterna(link)){
                mostrarLoader();
            }
        },true);

        document.addEventListener("submit",function(){
            mostrarLoader();
        },true);

        window.addEventListener("pageshow",ocultarLoader);
    }

    aplicarTema(leerTema(),false);

    if(document.readyState==="loading"){
        document.addEventListener("DOMContentLoaded",conectar);
    }else{
        conectar();
    }
})();
