(function(){
    function buscarAccionesRapidas(){
        return Array.from(
            document.querySelectorAll("section.seccion")
        ).find(function(section){
            const title=section.querySelector(
                ".seccion-titulo"
            );
            return title
                && title.textContent
                    .replace(/\s+/g," ")
                    .trim()
                    .toLowerCase()
                    === "acciones rápidas";
        });
    }

    function iniciar(){
        const menu=document.getElementById(
            "dvManagementMenu"
        );
        const toggle=document.getElementById(
            "dvManagementMenuToggle"
        );
        const overlay=document.getElementById(
            "dvManagementMenuOverlay"
        );
        const close=document.getElementById(
            "dvManagementMenuClose"
        );

        if(!menu || !toggle || !overlay) return;

        document.body.classList.add(
            "dv-management-menu-ready"
        );

        const acciones=buscarAccionesRapidas();
        if(acciones){
            acciones.remove();
        }

        function abrir(){
            menu.classList.add("is-open");
            overlay.classList.add("is-open");
            document.documentElement.classList.add(
                "dv-management-menu-open"
            );
            toggle.setAttribute(
                "aria-expanded",
                "true"
            );
            const first=menu.querySelector(
                "a,button"
            );
            if(first){
                first.focus({preventScroll:true});
            }
        }

        function cerrar(){
            menu.classList.remove("is-open");
            overlay.classList.remove("is-open");
            document.documentElement.classList.remove(
                "dv-management-menu-open"
            );
            toggle.setAttribute(
                "aria-expanded",
                "false"
            );
        }

        toggle.addEventListener(
            "click",
            function(){
                if(menu.classList.contains("is-open")){
                    cerrar();
                }else{
                    abrir();
                }
            }
        );

        overlay.addEventListener("click",cerrar);
        if(close){
            close.addEventListener("click",cerrar);
        }

        document.addEventListener(
            "keydown",
            function(event){
                if(event.key==="Escape") cerrar();
            }
        );

        window.addEventListener(
            "resize",
            function(){
                if(window.innerWidth>=1180){
                    cerrar();
                }
            }
        );
    }

    if(document.readyState==="loading"){
        document.addEventListener(
            "DOMContentLoaded",
            iniciar
        );
    }else{
        iniciar();
    }
})();


(function(){
    function cerrarMenusPedido(excepto){
        document.querySelectorAll(".dv-order-menu.is-open").forEach(function(menu){
            if(menu===excepto) return;
            menu.classList.remove("is-open");
            const boton=menu.querySelector(".dv-order-menu__toggle");
            if(boton) boton.setAttribute("aria-expanded","false");
        });
    }

    window.dvToggleOrderMenu=function(event,boton){
        if(event){
            event.preventDefault();
            event.stopPropagation();
        }

        const menu=boton && boton.closest(".dv-order-menu");
        if(!menu) return;

        const abrir=!menu.classList.contains("is-open");
        cerrarMenusPedido(menu);

        menu.classList.toggle("is-open",abrir);
        boton.setAttribute("aria-expanded",abrir ? "true" : "false");
    };

    document.addEventListener("click",function(event){
        if(event.target.closest(".dv-order-menu__panel")) return;
        cerrarMenusPedido();
    });

    document.addEventListener("keydown",function(event){
        if(event.key==="Escape"){
            cerrarMenusPedido();
        }
    });
})();


(function(){
    function iniciarSubmitLocks(){
        document.querySelectorAll(
            "form[data-dv-submit-lock]"
        ).forEach(function(form){
            form.addEventListener(
                "submit",
                function(event){
                    if(
                        form.dataset.dvSubmitting
                        === "1"
                    ){
                        event.preventDefault();
                        return;
                    }

                    form.dataset.dvSubmitting="1";

                    const buttons=Array.from(
                        form.querySelectorAll(
                            'button[type="submit"],input[type="submit"]'
                        )
                    );

                    buttons.forEach(function(button){
                        button.disabled=true;
                        button.setAttribute(
                            "aria-busy",
                            "true"
                        );

                        if(button.tagName==="BUTTON"){
                            if(
                                !button.dataset.dvOriginalText
                            ){
                                button.dataset.dvOriginalText=(
                                    button.textContent||""
                                );
                            }

                            button.textContent=(
                                button.dataset.dvLoadingText
                                || "GUARDANDO…"
                            );
                        }else{
                            if(
                                !button.dataset.dvOriginalValue
                            ){
                                button.dataset.dvOriginalValue=(
                                    button.value||""
                                );
                            }

                            button.value=(
                                button.dataset.dvLoadingText
                                || "GUARDANDO…"
                            );
                        }
                    });

                    const loader=document.getElementById(
                        "dvPageLoader"
                    );

                    if(loader){
                        const label=loader.querySelector(
                            ".dv-page-loader__text"
                        );

                        if(label){
                            label.textContent=(
                                form.dataset.dvLoadingLabel
                                || "Guardando archivo"
                            );
                        }

                        loader.classList.add(
                            "is-visible"
                        );
                        loader.setAttribute(
                            "aria-hidden",
                            "false"
                        );
                    }
                }
            );
        });
    }

    if(document.readyState==="loading"){
        document.addEventListener(
            "DOMContentLoaded",
            iniciarSubmitLocks
        );
    }else{
        iniciarSubmitLocks();
    }
})();
