import json

from django.core.cache import cache
from collections import defaultdict

from kits.models import Kit
from productos.image_environment import entorno_imagenes
from productos.image_models import ProductoImagen
from productos.models import Producto


CATALOG_ROTATOR_STYLE = r"""
<style id="dv-catalog-rotator-style">
/* Rotador simple para productos y kits no sensoriales. */
.media .dv-catalog-rotator,
.dv-kit-configurable-page .photo .dv-catalog-rotator{
    position:absolute;
    inset:0;
    z-index:0;
    overflow:hidden;
    background:#f2f5fa;
}
.media .dv-catalog-rotator img,
.dv-kit-configurable-page .photo .dv-catalog-rotator img{
    position:absolute!important;
    inset:0!important;
    width:100%!important;
    height:100%!important;
    display:block!important;
    object-fit:cover!important;
    object-position:center!important;
    opacity:0;
    transform:scale(1);
    transition:opacity .68s ease,transform .28s ease!important;
    pointer-events:none;
}
.media .dv-catalog-rotator img.is-active,
.dv-kit-configurable-page .photo .dv-catalog-rotator img.is-active{
    opacity:1;
}

.dv-kit-configurable-page .photo{
    position:relative!important;
}

/* Los kits sensoriales conservan SIEMPRE la identidad de collage 2x2. */
.catalog-item[data-kind="kit"][data-category*="sensorial"] .kit-collage,
.media .dv-sensory-grid{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    grid-template-rows:repeat(2,minmax(0,1fr))!important;
    width:100%!important;
    height:100%!important;
    gap:2px!important;
}
.catalog-item[data-kind="kit"][data-category*="sensorial"] .kit-collage .tile{
    grid-column:auto!important;
    grid-row:auto!important;
}
.media .dv-sensory-grid{
    position:absolute;
    inset:0;
    z-index:0;
    overflow:hidden;
    background:#f2f5fa;
}
.media .dv-sensory-slot{
    position:relative;
    min-width:0;
    min-height:0;
    overflow:hidden;
    background:#eef3f9;
}
.media .dv-sensory-slot img{
    position:absolute!important;
    inset:0!important;
    width:100%!important;
    height:100%!important;
    display:block!important;
    object-fit:cover!important;
    object-position:center!important;
    opacity:0;
    transform:scale(1);
    transition:opacity .68s ease,transform .28s ease!important;
    pointer-events:none;
}
.media .dv-sensory-slot img.is-active{
    opacity:1;
}

.media > .badge{
    z-index:4!important;
}

@media(hover:hover){
    .card:hover .dv-catalog-rotator img.is-active,
    .card:hover .dv-sensory-slot img.is-active,
    .preview:hover .dv-catalog-rotator img.is-active,
    .preview:hover .dv-sensory-slot img.is-active,
    .dv-kit-configurable-page .option:hover .dv-catalog-rotator img.is-active{
        transform:scale(1.025);
    }
}

@media(prefers-reduced-motion:reduce){
    .media .dv-catalog-rotator img,
    .media .dv-sensory-slot img,
    .dv-kit-configurable-page .photo .dv-catalog-rotator img{
        transition:none!important;
    }
}
</style>
"""


CATALOG_ROTATOR_SCRIPT = r"""
<script id="dv-catalog-rotator-script">
(() => {
    const productImages = __PRODUCT_IMAGES__;
    const kitImagePools = __KIT_IMAGE_POOLS__;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    const normalize = (value) =>
        (value || '')
            .toLocaleLowerCase('es')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .trim();

    const uniqueSlides = (slides, limit = null) => {
        const seen = new Set();
        const result = [];
        for (const slide of slides || []) {
            if (!slide || !slide.src || seen.has(slide.src)) continue;
            seen.add(slide.src);
            result.push(slide);
            if (limit && result.length >= limit) break;
        }
        return result;
    };

    const buildRotator = (media, slides) => {
        const normalized = uniqueSlides(slides, 4);
        if (!media || !normalized.length) return null;

        media.querySelectorAll(':scope > img, :scope > .kit-collage').forEach((node) => node.remove());

        const rotator = document.createElement('div');
        rotator.className = 'dv-catalog-rotator';
        rotator.dataset.current = '0';
        rotator.dataset.visible = '1';

        normalized.forEach((slide, index) => {
            const image = document.createElement('img');
            image.src = slide.src;
            image.alt = slide.alt || '';
            image.loading = index === 0 ? 'eager' : 'lazy';
            image.decoding = 'async';
            if (index === 0) image.classList.add('is-active');
            rotator.appendChild(image);
        });

        media.appendChild(rotator);
        return rotator;
    };

    const replaceSensorySlot = (slot, slide, delay = 0) => {
        if (!slot || !slide?.src) return;
        const current = slot.querySelector('img.is-active');
        if (current?.dataset.src === slide.src) return;

        window.setTimeout(() => {
            const next = document.createElement('img');
            next.src = slide.src;
            next.alt = slide.alt || 'Foto del kit';
            next.loading = 'lazy';
            next.decoding = 'async';
            next.dataset.src = slide.src;
            slot.appendChild(next);

            requestAnimationFrame(() => {
                next.classList.add('is-active');
                current?.classList.remove('is-active');
            });

            window.setTimeout(() => {
                if (current && current !== next) current.remove();
            }, 760);
        }, delay);
    };

    const buildSensoryGrid = (media, slides) => {
        const normalized = uniqueSlides(slides);
        if (!media || !normalized.length) return null;

        media.querySelectorAll(':scope > img, :scope > .kit-collage, :scope > .dv-catalog-rotator')
            .forEach((node) => node.remove());

        const grid = document.createElement('div');
        grid.className = 'dv-sensory-grid';
        grid.dataset.visible = '1';
        grid.dataset.offset = '0';
        grid.dataset.cursor = String(normalized.length > 4 ? 4 : 0);
        grid.dataset.slotCursor = '0';
        grid.__slides = normalized;

        for (let index = 0; index < 4; index += 1) {
            const slot = document.createElement('div');
            slot.className = 'dv-sensory-slot';
            const slide = normalized[index % normalized.length];

            const image = document.createElement('img');
            image.src = slide.src;
            image.alt = slide.alt || 'Foto del kit';
            image.loading = index < Math.min(normalized.length, 4) ? 'eager' : 'lazy';
            image.decoding = 'async';
            image.dataset.src = slide.src;
            image.classList.add('is-active');

            slot.appendChild(image);
            grid.appendChild(slot);
        }

        media.appendChild(grid);
        return grid;
    };

    const simpleRotators = [];
    const sensoryGrids = [];

    document.querySelectorAll('.catalog-item[data-kind="producto"] .media').forEach((media) => {
        const current = media.querySelector(':scope > img');
        if (!current) return;

        const rawSrc = current.getAttribute('src') || '';
        const urls = productImages[rawSrc] || productImages[current.src] || [rawSrc];
        const slides = urls.map((src) => ({src, alt: current.alt || ''}));
        const rotator = buildRotator(media, slides);
        if (rotator) simpleRotators.push(rotator);
    });

    // En el detalle de kits reutilizamos exactamente el mismo pool de dos
    // fotos por producto que usa el listado público. Esto incluye tanto las
    // opciones de un kit libre como la composición visual de un kit fijo.
    document.querySelectorAll('.dv-kit-configurable-page .option .photo').forEach((photo) => {
        const current = photo.querySelector(':scope > img');
        if (!current) return;

        const rawSrc = current.getAttribute('src') || '';
        const urls = productImages[rawSrc] || productImages[current.src] || [rawSrc];
        const slides = urls.map((src) => ({src, alt: current.alt || ''}));
        const rotator = buildRotator(photo, slides);
        if (rotator) simpleRotators.push(rotator);
    });

    const kitCards = [...document.querySelectorAll('.catalog-item[data-kind="kit"]')];
    kitCards.forEach((card, index) => {
        const media = card.querySelector('.media');
        if (!media) return;

        const poolSource =
            kitImagePools[String(card.dataset.kitId || '')]
            || kitImagePools[index]
            || [];
        const pool = poolSource.map((item) => ({
            src: item.src,
            alt: item.alt || 'Foto del kit',
        }));
        const fallback = [...media.querySelectorAll('.kit-collage img')].map((image) => ({
            src: image.getAttribute('src') || image.src,
            alt: image.alt || 'Foto del kit',
        }));
        const slides = pool.length ? pool : fallback;
        if (!slides.length) return;

        const isSensory = normalize(card.dataset.category).includes('sensorial');
        if (isSensory) {
            const grid = buildSensoryGrid(media, slides);
            if (grid) sensoryGrids.push(grid);
            return;
        }

        const rotator = buildRotator(media, slides);
        if (rotator) simpleRotators.push(rotator);
    });

    const observeVisibility = (elements) => {
        if (!('IntersectionObserver' in window)) return;
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                entry.target.dataset.visible = entry.isIntersecting ? '1' : '0';
            });
        }, {rootMargin: '120px 0px'});
        elements.forEach((element) => observer.observe(element));
    };

    observeVisibility([...simpleRotators, ...sensoryGrids]);

    if (reduceMotion) return;

    const advanceSimple = (rotator) => {
        const slides = [...rotator.querySelectorAll('img')];
        if (slides.length < 2) return;
        const current = Number(rotator.dataset.current || 0);
        const next = (current + 1) % slides.length;
        slides[current]?.classList.remove('is-active');
        slides[next]?.classList.add('is-active');
        rotator.dataset.current = String(next);
    };

    const advanceSensory = (grid) => {
        const slides = grid.__slides || [];
        const slots = [...grid.querySelectorAll('.dv-sensory-slot')];
        const total = slides.length;
        if (!total || !slots.length) return;

        // Exactamente 4 fotos: collage fijo, sin animación.
        if (total === 4) return;

        if (total < 4) {
            // Con 2 o 3 fotos mantenemos 4 cuadrantes y desplazamos el patrón.
            // Con una sola foto el 2x2 queda estable porque no existe una
            // segunda imagen real con la que alternar.
            if (total === 1) return;
            const offset = (Number(grid.dataset.offset || 0) + 1) % total;
            grid.dataset.offset = String(offset);
            slots.forEach((slot, index) => {
                replaceSensorySlot(slot, slides[(index + offset) % total], index * 85);
            });
            return;
        }

        // Más de 4: reemplazamos un cuadrante por vez. Elegimos una imagen que
        // no esté visible para conservar cuatro fotos distintas siempre que sea posible.
        let cursor = Number(grid.dataset.cursor || 4) % total;
        const slotIndex = Number(grid.dataset.slotCursor || 0) % 4;
        const visible = new Set(
            slots
                .map((slot) => slot.querySelector('img.is-active')?.dataset.src)
                .filter(Boolean),
        );

        let selected = slides[cursor];
        for (let attempt = 0; attempt < total; attempt += 1) {
            const candidate = slides[(cursor + attempt) % total];
            if (!visible.has(candidate.src)) {
                selected = candidate;
                cursor = (cursor + attempt) % total;
                break;
            }
        }

        replaceSensorySlot(slots[slotIndex], selected);
        grid.dataset.cursor = String((cursor + 1) % total);
        grid.dataset.slotCursor = String((slotIndex + 1) % 4);
    };

    window.setInterval(() => {
        if (document.hidden) return;

        simpleRotators.forEach((rotator) => {
            if (rotator.dataset.visible === '0' || rotator.matches(':hover')) return;
            advanceSimple(rotator);
        });

        sensoryGrids.forEach((grid) => {
            if (grid.dataset.visible === '0' || grid.matches(':hover')) return;
            advanceSensory(grid);
        });
    }, 3000);
})();
</script>
"""


def _product_image_groups():
    grouped = defaultdict(list)
    imagenes = (
        ProductoImagen.objects
        .filter(ambiente=entorno_imagenes())
        .order_by('producto_id', 'orden', 'id')
    )
    for imagen in imagenes:
        if len(grouped[imagen.producto_id]) < 2:
            grouped[imagen.producto_id].append(imagen)
    return grouped


def _product_image_map(grouped=None):
    grouped = grouped or _product_image_groups()
    payload = {}
    for grupo in grouped.values():
        if not grupo:
            continue
        principal = next((imagen for imagen in grupo if imagen.orden == 1), grupo[0])
        payload[principal.url] = [imagen.url for imagen in grupo]
    return payload


def _kit_image_pools(grouped=None):
    """Devuelve las fotos de cada kit en el mismo orden usado por el catálogo."""
    grouped = grouped or _product_image_groups()

    kits = list(
        Kit.objects
        .filter(activo=True)
        .select_related('tipo_producto')
        .prefetch_related('componentes__producto')
        .order_by('nombre')
    )

    tipos_libres = {
        kit.tipo_producto_id
        for kit in kits
        if kit.modalidad != 'FIJO' and kit.tipo_producto_id
    }
    productos_por_tipo = defaultdict(list)
    if tipos_libres:
        for producto in (
            Producto.objects
            .filter(
                activo=True,
                solo_produccion=False,
                tipo_id__in=tipos_libres,
            )
            .order_by('tipo__nombre', 'nombre')
        ):
            productos_por_tipo[producto.tipo_id].append(producto)

    pools = []
    for kit in kits:
        if kit.modalidad == 'FIJO':
            productos = [
                componente.producto
                for componente in kit.componentes.all()
                if componente.producto_id
            ]
        else:
            productos = productos_por_tipo.get(kit.tipo_producto_id, [])

        seen_urls = set()
        fotos = []
        for producto in productos:
            for imagen in grouped.get(producto.id, []):
                if not imagen.url or imagen.url in seen_urls:
                    continue
                seen_urls.add(imagen.url)
                fotos.append({
                    'src': imagen.url,
                    'alt': producto.nombre,
                })

        pools.append(fotos)

    return pools


class CatalogRotatorMiddleware:
    """Galerías rotativas para productos y collages 2x2 para kits sensoriales."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        view_name = match.view_name if match else ''

        if (
            view_name not in {
                'catalogo',
                'catalogo_legacy',
                'catalogo_productos',
                'catalogo_categoria',
                'catalogo_categoria_productos',
                'catalogo_categoria_kits',
                'catalogo_kits',
                'catalogo_kit_detalle',
            }
            or response.status_code != 200
            or getattr(response, 'streaming', False)
            or 'text/html' not in response.get('Content-Type', '')
        ):
            return response

        try:
            contenido = response.content.decode(response.charset or 'utf-8')
        except (AttributeError, UnicodeDecodeError):
            return response

        if 'dv-catalog-rotator-style' not in contenido and '</head>' in contenido:
            contenido = contenido.replace(
                '</head>',
                CATALOG_ROTATOR_STYLE + '\n</head>',
                1,
            )

        if 'dv-catalog-rotator-script' not in contenido and '</body>' in contenido:
            cache_key = (
                "dv-catalog-rotator-payload-v1:"
                + entorno_imagenes()
            )
            payloads = cache.get(cache_key)
            if payloads is None:
                grouped = _product_image_groups()
                kit_pools = _kit_image_pools(grouped)
                kit_ids = list(
                    Kit.objects
                    .filter(activo=True)
                    .order_by('nombre')
                    .values_list('id', flat=True)
                )
                payloads = {
                    "productos": _product_image_map(grouped),
                    "kits": {
                        str(kit_id): pool
                        for kit_id, pool in zip(kit_ids, kit_pools)
                    },
                }
                cache.set(cache_key, payloads, 60)

            product_payload = json.dumps(
                payloads["productos"],
                ensure_ascii=False,
            ).replace('</', '<\\/')
            kit_payload = json.dumps(
                payloads["kits"],
                ensure_ascii=False,
            ).replace('</', '<\\/')

            script = (
                CATALOG_ROTATOR_SCRIPT
                .replace('__PRODUCT_IMAGES__', product_payload)
                .replace('__KIT_IMAGE_POOLS__', kit_payload)
            )
            contenido = contenido.replace('</body>', script + '\n</body>', 1)

        encoded = contenido.encode(response.charset or 'utf-8')
        response.content = encoded
        response['Content-Length'] = str(len(encoded))
        return response
