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

    aplicarTema(leerTema(),false);

    function conectar(){
        const check=document.getElementById("dvThemeToggle");
        if(!check) return;

        aplicarTema(leerTema(),false);

        check.addEventListener("change",function(){
            aplicarTema(
                check.checked?"dark":"light",
                true
            );
        });
    }

    if(document.readyState==="loading"){
        document.addEventListener("DOMContentLoaded",conectar);
    }else{
        conectar();
    }
})();
