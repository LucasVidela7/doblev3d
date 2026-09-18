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

    function conectar(){
        const check=document.getElementById("dvThemeToggle");
        aplicarTema(leerTema(),false);

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
