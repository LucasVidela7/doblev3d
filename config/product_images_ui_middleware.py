import html as html_lib
import json
import re

from django.urls import reverse

from productos.image_environment import (
    ambientes_imagenes_lectura,
    clave_imagen_lectura,
    entorno_imagenes,
)
from productos.image_models import ProductoImagen
from productos.imagekit_service import imagekit_configurado


STYLE = r"""
<style id="dv-product-images-style">
.dv-producto-fotos{
    margin-bottom:14px;
    padding:14px;
    border:1px solid #e4e7eb;
    border-radius:16px;
    background:#fff;
}
.dv-producto-fotos-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin-bottom:10px;
}
.dv-producto-fotos-title{font-size:10px;font-weight:900;color:#555d66}
.dv-producto-fotos-link{
    min-height:38px;
    padding:0 12px;
    border:1px solid #d9dee5;
    border-radius:11px;
    color:#24272b;
    background:#fff;
    text-decoration:none;
    font-size:9px;
    font-weight:900;
    display:inline-flex;
    align-items:center;
    justify-content:center;
}
.dv-producto-fotos-grid{display:grid;grid-template-columns:repeat(2,minmax(0,220px));gap:10px}
.dv-producto-foto{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:#f0f2f4;border:1px solid #e5e7eb}
.dv-producto-foto img{width:100%;height:100%;object-fit:cover;display:block}
.dv-producto-foto span{position:absolute;left:8px;bottom:8px;padding:5px 7px;border-radius:999px;background:rgba(35,38,43,.84);color:#fff;font-size:7px;font-weight:900}
.dv-producto-foto-vacia{display:flex;align-items:center;justify-content:center;color:#969ba2;font-size:10px;font-weight:900}
@media(max-width:650px){.dv-producto-fotos-grid{grid-template-columns:1fr 1fr}.dv-producto-fotos-head{align-items:flex-start}.dv-producto-fotos-link{min-height:42px}}
</style>
"""


EDIT_PHOTOS_STYLE = r"""
<style id="dv-edit-product-photos-style">
.dv-edit-fotos-card{overflow:hidden}
.dv-fotos-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}
.dv-fotos-head-copy{min-width:0}
.dv-fotos-head .titulo{margin-bottom:4px}
.dv-fotos-sub{color:#747980;font-size:10px;line-height:1.45}
.dv-fotos-count{flex:0 0 auto;min-height:30px;padding:0 10px;border-radius:999px;background:#f3f5f7;color:#555d66;font-size:9px;font-weight:900;display:inline-flex;align-items:center}
.dv-fotos-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:stretch}
.dv-fotos-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;min-width:0}
.dv-foto-slot{position:relative;aspect-ratio:1/1;min-width:0;overflow:hidden;border:1px solid #e1e5ea;border-radius:16px;background:#f4f6f8}
.dv-foto-slot img{width:100%;height:100%;display:block;object-fit:cover}
.dv-foto-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;padding:14px;color:#989da4;text-align:center}
.dv-foto-empty-icon{font-size:25px;line-height:1;font-weight:400}
.dv-foto-empty span:last-child{font-size:8px;font-weight:900;letter-spacing:.04em}
.dv-foto-actions{position:absolute;z-index:3;right:8px;top:8px;display:flex;gap:6px}
.dv-foto-action{width:42px;height:42px;padding:0;border:1px solid rgba(255,255,255,.72);border-radius:12px;background:rgba(35,38,43,.86);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:17px;line-height:1;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.15);backdrop-filter:blur(9px);-webkit-tap-highlight-color:transparent}
.dv-foto-action:disabled{cursor:default;background:rgba(35,38,43,.58);opacity:.9}
.dv-foto-action.dv-delete{background:rgba(130,42,42,.88)}
.dv-foto-badge{position:absolute;z-index:2;left:8px;bottom:8px;min-height:28px;padding:0 9px;border-radius:999px;background:rgba(35,38,43,.84);color:#fff;display:inline-flex;align-items:center;font-size:8px;font-weight:900;backdrop-filter:blur(8px)}
.dv-foto-badge.dv-main{background:rgba(31,99,58,.90)}
.dv-foto-uploading:after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(20,24,30,.58),rgba(20,24,30,.05) 55%);pointer-events:none}
.dv-upload-progress{position:absolute;z-index:4;left:10px;right:10px;bottom:10px}
.dv-upload-progress-track{height:7px;border-radius:999px;background:rgba(255,255,255,.34);overflow:hidden}
.dv-upload-progress-bar{height:100%;border-radius:inherit;background:#fff;transition:width .12s linear}
.dv-upload-progress-text{margin-bottom:6px;color:#fff;font-size:9px;font-weight:900;text-shadow:0 1px 3px rgba(0,0,0,.28)}
.dv-dropzone{width:100%;min-height:100%;padding:18px;border:1.5px dashed #cbd2da;border-radius:16px;background:#fafbfc;color:#565e68;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;text-align:center;cursor:pointer;transition:border-color .15s ease,background .15s ease,transform .15s ease;-webkit-tap-highlight-color:transparent}
.dv-dropzone-icon{width:48px;height:48px;border-radius:15px;background:#24272b;color:#fff;display:grid;place-items:center;font-size:25px;line-height:1}
.dv-dropzone strong{font-size:11px}
.dv-dropzone span{max-width:225px;color:#7a8088;font-size:9px;line-height:1.45}
.dv-dropzone.is-over{border-color:#4d6f98;background:#f1f6fc;transform:translateY(-1px)}
.dv-dropzone.is-disabled{cursor:default;border-style:solid;background:#f5f6f7;color:#9ba0a6}
.dv-dropzone.is-disabled .dv-dropzone-icon{background:#a7acb2}
.dv-fotos-status{display:none;margin-top:12px;padding:10px 12px;border-radius:11px;font-size:10px;font-weight:800;line-height:1.45}
.dv-fotos-status.is-visible{display:block}
.dv-fotos-status.is-ok{background:#eef8f1;color:#2f6b42;border:1px solid #cfe5d5}
.dv-fotos-status.is-error{background:#fff3f3;color:#913737;border:1px solid #efd0d0}
.dv-fotos-status.is-info{background:#f4f7fb;color:#516071;border:1px solid #dde4ed}
.dv-fotos-config-warning{margin-bottom:12px;padding:10px 12px;border-radius:11px;background:#fff8e8;border:1px solid #eadcaf;color:#755d18;font-size:10px;font-weight:800;line-height:1.45}
@media(hover:hover){.dv-foto-action:hover{transform:translateY(-1px)}.dv-dropzone:not(.is-disabled):hover{border-color:#9eabb9;background:#f7f9fb}}
@media(max-width:860px){.dv-fotos-layout{grid-template-columns:1fr}.dv-dropzone{min-height:150px}}
@media(max-width:520px){.dv-edit-fotos-card{padding:14px!important}.dv-fotos-head{gap:8px}.dv-fotos-grid{gap:8px}.dv-foto-slot{border-radius:13px}.dv-foto-actions{right:6px;top:6px;gap:4px}.dv-foto-action{width:38px;height:38px;border-radius:11px;font-size:16px}.dv-foto-badge{left:6px;bottom:6px;min-height:25px;padding:0 7px;font-size:7px}.dv-dropzone{min-height:138px;padding:15px}.dv-dropzone-icon{width:44px;height:44px;border-radius:13px}.dv-fotos-sub{font-size:9px}}
</style>
"""


EDIT_PHOTOS_SCRIPT = r"""
<script id="dv-edit-product-photos-script">
(() => {
    const root = document.getElementById("dv-editar-fotos");
    if (!root) return;

    const config = __CONFIG__;
    const gallery = document.getElementById("dv-fotos-grid");
    const dropzone = document.getElementById("dv-fotos-dropzone");
    const input = document.getElementById("dv-fotos-input");
    const status = document.getElementById("dv-fotos-status");
    const count = document.getElementById("dv-fotos-count");
    const csrf = document.querySelector('#form-producto input[name="csrfmiddlewaretoken"]');
    const MAX_FOTOS = 2;
    const MAX_BYTES = 15 * 1024 * 1024;

    let images = Array.isArray(config.images) ? config.images : [];
    let pending = null;
    let busy = false;

    const escapeHtml = (value) => String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const actionUrl = (template, id) => template.replace("/0/", `/${id}/`);

    const showStatus = (message, type = "info") => {
        status.textContent = message || "";
        status.className = `dv-fotos-status is-visible is-${type}`;
    };

    const clearStatus = () => {
        status.textContent = "";
        status.className = "dv-fotos-status";
    };

    const imageCard = (image) => {
        const principal = !!image.principal;
        return `
            <div class="dv-foto-slot" data-image-id="${image.id}">
                <img src="${escapeHtml(image.preview_url || image.url)}" alt="Foto del producto">
                <div class="dv-foto-actions">
                    <button type="button" class="dv-foto-action" data-photo-action="principal" data-image-id="${image.id}" ${principal ? "disabled" : ""} aria-label="${principal ? "Foto principal" : "Marcar como principal"}" title="${principal ? "Foto principal" : "Marcar como principal"}">★</button>
                    <button type="button" class="dv-foto-action dv-delete" data-photo-action="delete" data-image-id="${image.id}" aria-label="Eliminar foto" title="Eliminar foto">🗑</button>
                </div>
                <span class="dv-foto-badge ${principal ? "dv-main" : ""}">${principal ? "★ PRINCIPAL" : "SECUNDARIA"}</span>
            </div>`;
    };

    const pendingCard = () => {
        if (!pending) return "";
        return `
            <div class="dv-foto-slot dv-foto-uploading">
                <img src="${escapeHtml(pending.preview)}" alt="Vista previa de la foto">
                <div class="dv-upload-progress">
                    <div class="dv-upload-progress-text">SUBIENDO · ${pending.progress}%</div>
                    <div class="dv-upload-progress-track"><div class="dv-upload-progress-bar" style="width:${pending.progress}%"></div></div>
                </div>
            </div>`;
    };

    const emptyCard = (position) => `
        <div class="dv-foto-slot dv-foto-empty">
            <span class="dv-foto-empty-icon">＋</span>
            <span>FOTO ${position}</span>
        </div>`;

    const render = () => {
        const cards = images.map(imageCard);
        if (pending && cards.length < MAX_FOTOS) cards.push(pendingCard());
        while (cards.length < MAX_FOTOS) cards.push(emptyCard(cards.length + 1));
        gallery.innerHTML = cards.join("");
        count.textContent = `${images.length}/2 FOTOS`;

        const full = images.length >= MAX_FOTOS;
        const disabled = full || busy || !config.enabled;
        dropzone.classList.toggle("is-disabled", disabled);
        dropzone.setAttribute("aria-disabled", disabled ? "true" : "false");
        dropzone.querySelector("strong").textContent = full
            ? "Ya cargaste las 2 fotos"
            : (busy ? "Subiendo foto…" : "Arrastrá o seleccioná fotos");
        dropzone.querySelector("span:last-child").textContent = full
            ? "Podés eliminar una foto para reemplazarla."
            : "Formato recomendado 1:1 · máximo 15 MB por imagen";
    };

    const normalizeResponse = (xhr) => {
        let data = null;
        try { data = JSON.parse(xhr.responseText || "{}"); } catch (_) {}
        if (!data) data = {};
        if (xhr.status < 200 || xhr.status >= 300 || !data.ok) {
            throw new Error(data.message || "No se pudo completar la operación.");
        }
        return data;
    };

    const uploadOne = (file) => new Promise((resolve, reject) => {
        if (!file || !file.type || !file.type.startsWith("image/")) {
            reject(new Error("Seleccioná un archivo de imagen válido."));
            return;
        }
        if (file.size > MAX_BYTES) {
            reject(new Error(`${file.name}: supera el máximo permitido de 15 MB.`));
            return;
        }

        const preview = URL.createObjectURL(file);
        pending = { preview, progress: 0 };
        render();
        clearStatus();

        const xhr = new XMLHttpRequest();
        xhr.open("POST", config.upload_url, true);
        xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
        xhr.setRequestHeader("Accept", "application/json");
        if (csrf?.value) xhr.setRequestHeader("X-CSRFToken", csrf.value);

        xhr.upload.addEventListener("progress", (event) => {
            if (!pending || !event.lengthComputable) return;
            pending.progress = Math.min(99, Math.round((event.loaded / event.total) * 100));
            render();
        });

        xhr.addEventListener("load", () => {
            try {
                const data = normalizeResponse(xhr);
                images = data.imagenes || images;
                showStatus(data.message || "Foto cargada correctamente.", "ok");
                resolve(data);
            } catch (error) {
                reject(error);
            } finally {
                URL.revokeObjectURL(preview);
                pending = null;
                render();
            }
        });

        xhr.addEventListener("error", () => {
            URL.revokeObjectURL(preview);
            pending = null;
            render();
            reject(new Error("Se perdió la conexión durante la carga."));
        });

        const body = new FormData();
        body.append("imagen", file, file.name);
        xhr.send(body);
    });

    const processFiles = async (fileList) => {
        if (busy || !config.enabled) return;
        const available = MAX_FOTOS - images.length;
        if (available <= 0) {
            showStatus("Este producto ya tiene el máximo de 2 fotos.", "info");
            return;
        }

        const files = [...(fileList || [])].filter(Boolean);
        if (!files.length) return;
        const selected = files.slice(0, available);
        if (files.length > available) {
            showStatus(`Solo quedan ${available} espacio${available === 1 ? "" : "s"}. Se cargarán las primeras ${available} foto${available === 1 ? "" : "s"}.`, "info");
        }

        busy = true;
        render();
        for (const file of selected) {
            try {
                await uploadOne(file);
            } catch (error) {
                showStatus(error.message || "No se pudo subir la foto.", "error");
            }
        }
        busy = false;
        input.value = "";
        render();
    };

    const postAction = async (url) => {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
                ...(csrf?.value ? {"X-CSRFToken": csrf.value} : {}),
            },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) throw new Error(data.message || "No se pudo completar la operación.");
        images = data.imagenes || images;
        render();
        showStatus(data.message || "Cambios guardados.", "ok");
    };

    dropzone.addEventListener("click", () => {
        if (dropzone.classList.contains("is-disabled")) return;
        input.click();
    });
    dropzone.addEventListener("keydown", (event) => {
        if ((event.key === "Enter" || event.key === " ") && !dropzone.classList.contains("is-disabled")) {
            event.preventDefault();
            input.click();
        }
    });
    input.addEventListener("change", () => processFiles(input.files));

    ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        if (!dropzone.classList.contains("is-disabled")) dropzone.classList.add("is-over");
    }));
    ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.remove("is-over");
    }));
    dropzone.addEventListener("drop", (event) => processFiles(event.dataTransfer?.files));

    gallery.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-photo-action]");
        if (!button || busy) return;
        const id = Number(button.dataset.imageId);
        if (!id) return;
        const action = button.dataset.photoAction;

        if (action === "delete" && !window.confirm("¿Eliminar esta foto del producto y de ImageKit?")) return;

        busy = true;
        render();
        try {
            const url = action === "delete"
                ? actionUrl(config.delete_template, id)
                : actionUrl(config.principal_template, id);
            await postAction(url);
        } catch (error) {
            showStatus(error.message || "No se pudo completar la operación.", "error");
        } finally {
            busy = false;
            render();
        }
    });

    render();
})();
</script>
"""


CATALOG_STYLE = r"""
<style id="dv-catalog-square-style">
/*
   El catálogo está pensado para material fotográfico 1:1.
   La foto es el elemento principal y no debe recortarse a formatos apaisados.
*/
.media{
    aspect-ratio:1 / 1!important;
    background:#f2f5fa!important;
}
.media img,
.kit-collage img{
    width:100%!important;
    height:100%!important;
    object-fit:cover!important;
    object-position:center!important;
}

/* Grid más cercano a una tienda: aprovecha el ancho sin hacer tarjetas gigantes. */
.grid{
    grid-template-columns:repeat(auto-fit,minmax(260px,1fr))!important;
    gap:18px!important;
    align-items:stretch!important;
}
.card:not(.hidden-by-filter){
    display:flex!important;
    min-width:0!important;
    flex-direction:column!important;
    overflow:hidden!important;
    border-radius:20px!important;
}
.catalog-item.hidden-by-filter,
.section.hidden-by-filter{
    display:none!important;
}
.content{
    display:flex!important;
    flex:1 1 auto!important;
    flex-direction:column!important;
    padding:17px!important;
}
.title{
    display:-webkit-box;
    overflow:hidden;
    -webkit-box-orient:vertical;
    -webkit-line-clamp:2;
}
.detail{
    min-height:2.75em!important;
    display:-webkit-box;
    overflow:hidden;
    -webkit-box-orient:vertical;
    -webkit-line-clamp:2;
}
.price-row{
    margin-top:auto!important;
}

/* Los kits conservan el collage, pero dentro de un lienzo cuadrado. */
.kit-collage{
    width:100%!important;
    height:100%!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    grid-template-rows:repeat(2,minmax(0,1fr))!important;
}
.kit-collage .tile{
    min-width:0!important;
    min-height:0!important;
}

/* Hero más corto: el catálogo empieza antes y la fotografía gana protagonismo. */
.hero{
    padding:30px 0 24px!important;
}
.hero-card{
    padding:clamp(28px,4vw,50px)!important;
    border-radius:28px!important;
}
.hero p{
    margin-top:16px!important;
}

@media(hover:hover){
    .media img{
        transition:transform .28s ease!important;
    }
    .card:hover .media > img{
        transform:scale(1.025);
    }
}

@media(max-width:900px){
    .grid{
        grid-template-columns:repeat(auto-fit,minmax(250px,1fr))!important;
        gap:15px!important;
    }
}

@media(max-width:580px){
    .shell{
        width:min(100% - 16px,1180px)!important;
    }
    .hero{
        padding:14px 0 18px!important;
    }
    .hero-card{
        padding:24px 20px!important;
        border-radius:22px!important;
    }
    .grid{
        grid-template-columns:repeat(2,minmax(0,1fr))!important;
        gap:8px!important;
    }
    .card:not(.hidden-by-filter){
        border-radius:14px!important;
    }
    .media{
        aspect-ratio:1 / 1!important;
    }
    .content{
        padding:10px!important;
    }
    .title{
        min-height:2.25em!important;
        font-size:.86rem!important;
        line-height:1.12!important;
    }
    .detail{
        display:none!important;
    }
    .price-row{
        gap:7px!important;
        padding-top:8px!important;
    }
    .price{
        font-size:.98rem!important;
    }
}
</style>
"""


def _imagenes_payload(imagenes):
    return [
        {
            "id": imagen.id,
            "url": imagen.url,
            "preview_url": imagen.thumbnail_url or imagen.url,
            "orden": imagen.orden,
            "principal": imagen.orden == 1,
            "nombre": imagen.nombre_archivo,
            "ancho": imagen.ancho,
            "alto": imagen.alto,
            "tamano_bytes": imagen.tamano_bytes,
        }
        for imagen in imagenes
    ]


def _bloque_editar_fotos(configurado):
    warning = ""
    if not configurado:
        warning = (
            '<div class="dv-fotos-config-warning">'
            "IMAGEKIT NO ESTÁ CONFIGURADO EN ESTE ENTORNO · "
            "La galería se muestra, pero la carga está deshabilitada."
            "</div>"
        )
    return (
        '<div class="tarjeta dv-edit-fotos-card" id="dv-editar-fotos">'
        '<div class="dv-fotos-head">'
        '<div class="dv-fotos-head-copy">'
        '<div class="titulo">FOTOS DEL PRODUCTO</div>'
        '<div class="dv-fotos-sub">Administralas acá mismo. Al seleccionar o arrastrar una imagen se sube a ImageKit automáticamente, sin guardar primero el formulario.</div>'
        '</div>'
        '<span id="dv-fotos-count" class="dv-fotos-count">0/2 FOTOS</span>'
        '</div>'
        + warning
        + '<div class="dv-fotos-layout">'
        '<div id="dv-fotos-grid" class="dv-fotos-grid"></div>'
        '<button type="button" id="dv-fotos-dropzone" class="dv-dropzone" aria-label="Seleccionar o arrastrar fotos">'
        '<span class="dv-dropzone-icon" aria-hidden="true">＋</span>'
        '<strong>Arrastrá o seleccioná fotos</strong>'
        '<span>Formato recomendado 1:1 · máximo 15 MB por imagen</span>'
        '</button>'
        '</div>'
        '<input id="dv-fotos-input" type="file" accept="image/*" multiple hidden>'
        '<div id="dv-fotos-status" class="dv-fotos-status" role="status" aria-live="polite"></div>'
        '</div>'
    )


class ProductImagesUIMiddleware:
    """UI de imágenes de producto y ajustes visuales del catálogo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        view_name = match.view_name if match else ""

        if (
            not match
            or response.status_code != 200
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        # Catálogo público: las fotografías se producen en formato cuadrado 1:1.
        if view_name in {"catalogo_productos", "catalogo_kits"}:
            try:
                contenido = response.content.decode(response.charset or "utf-8")
            except (AttributeError, UnicodeDecodeError):
                return response

            if "dv-catalog-square-style" not in contenido and "</head>" in contenido:
                contenido = contenido.replace(
                    "</head>",
                    CATALOG_STYLE + "\n</head>",
                    1,
                )

            encoded = contenido.encode(response.charset or "utf-8")
            response.content = encoded
            response["Content-Length"] = str(len(encoded))
            return response

        if view_name not in {"productos:detalle", "productos:editar"}:
            return response

        producto_id = match.kwargs.get("producto_id")
        if not producto_id:
            return response

        ambiente_actual = entorno_imagenes()
        ambientes = (
            (ambiente_actual,)
            if view_name == "productos:editar"
            else ambientes_imagenes_lectura()
        )
        imagenes = list(
            ProductoImagen.objects
            .filter(
                producto_id=producto_id,
                ambiente__in=ambientes,
            )
            .order_by("orden", "id")
        )
        imagenes.sort(key=clave_imagen_lectura)
        imagenes = imagenes[:2]

        try:
            contenido = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if view_name == "productos:editar":
            if "dv-edit-product-photos-style" not in contenido and "</head>" in contenido:
                contenido = contenido.replace(
                    "</head>",
                    EDIT_PHOTOS_STYLE + "\n</head>",
                    1,
                )

            if 'id="dv-editar-fotos"' not in contenido:
                marker = '<div class="tarjeta" id="bloque-simple">'
                if marker in contenido:
                    contenido = contenido.replace(
                        marker,
                        _bloque_editar_fotos(imagekit_configurado()) + marker,
                        1,
                    )

            config = {
                "enabled": imagekit_configurado(),
                "images": _imagenes_payload(imagenes),
                "upload_url": reverse("productos:imagen_subir", args=[producto_id]),
                "principal_template": reverse(
                    "productos:imagen_principal",
                    args=[producto_id, 0],
                ),
                "delete_template": reverse(
                    "productos:imagen_eliminar",
                    args=[producto_id, 0],
                ),
            }
            script = EDIT_PHOTOS_SCRIPT.replace(
                "__CONFIG__",
                json.dumps(config, ensure_ascii=False).replace("</", "<\\/"),
            )
            if "dv-edit-product-photos-script" not in contenido and "</body>" in contenido:
                contenido = contenido.replace("</body>", script + "\n</body>", 1)

            encoded = contenido.encode(response.charset or "utf-8")
            response.content = encoded
            response["Content-Length"] = str(len(encoded))
            return response

        if "dv-product-images-style" not in contenido and "</head>" in contenido:
            contenido = contenido.replace("</head>", STYLE + "\n</head>", 1)

        editar_fotos_url = reverse("productos:editar", args=[producto_id]) + "#dv-editar-fotos"
        boton = (
            f'<a class="btn" href="{html_lib.escape(editar_fotos_url)}">'
            f'📷 FOTOS {len(imagenes)}/2</a>'
        )
        if "📷 FOTOS" not in contenido:
            contenido = re.sub(
                r'(<a class="btn dark" href="[^"]+">EDITAR PRODUCTO</a>)',
                r"\1" + boton,
                contenido,
                count=1,
            )

        fotos_html = []
        for imagen in imagenes:
            src = imagen.thumbnail_url or imagen.url
            rol = "PRINCIPAL" if imagen.orden == 1 else "SECUNDARIA"
            fotos_html.append(
                '<div class="dv-producto-foto">'
                f'<img src="{html_lib.escape(src)}" alt="Foto de producto">'
                f'<span>{rol}</span></div>'
            )
        while len(fotos_html) < 2:
            fotos_html.append(
                '<a class="dv-producto-foto dv-producto-foto-vacia" '
                f'href="{html_lib.escape(editar_fotos_url)}">+ AGREGAR FOTO</a>'
            )

        bloque = (
            '<div id="dv-producto-fotos-panel" class="dv-producto-fotos">'
            '<div class="dv-producto-fotos-head">'
            '<div class="dv-producto-fotos-title">FOTOS DEL PRODUCTO</div>'
            f'<a class="dv-producto-fotos-link" href="{html_lib.escape(editar_fotos_url)}">EDITAR FOTOS</a>'
            '</div><div class="dv-producto-fotos-grid">'
            + "".join(fotos_html)
            + "</div></div>"
        )

        if 'id="dv-producto-fotos-panel"' not in contenido:
            contenido = contenido.replace(
                '<div class="res">',
                bloque + '<div class="res">',
                1,
            )

        encoded = contenido.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
