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
