import json
from collections import defaultdict

from productos.image_environment import entorno_imagenes
from productos.image_models import ProductoImagen


CATALOG_ROTATOR_STYLE = r"""
<style id="dv-catalog-rotator-style">
.media .dv-catalog-rotator{
    position:absolute;
    inset:0;
    z-index:0;
    overflow:hidden;
    background:#f2f5fa;
}
.media .dv-catalog-rotator img{
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
.media .dv-catalog-rotator img.is-active{
    opacity:1;
}
.media > .badge{
    z-index:4!important;
}
@media(hover:hover){
    .card:hover .dv-catalog-rotator img.is-active{
        transform:scale(1.025);
    }
}
@media(prefers-reduced-motion:reduce){
    .media .dv-catalog-rotator img{
        transition:none!important;
    }
}
</style>
"""


CATALOG_ROTATOR_SCRIPT = r"""
<script id="dv-catalog-rotator-script">
(() => {
    const productImages = __PRODUCT_IMAGES__;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    const uniqueSlides = (slides, limit = 4) => {
        const seen = new Set();
        const result = [];
        for (const slide of slides) {
            if (!slide || !slide.src || seen.has(slide.src)) continue;
            seen.add(slide.src);
            result.push(slide);
            if (result.length >= limit) break;
        }
        return result;
    };

    const buildRotator = (media, slides) => {
        const normalized = uniqueSlides(slides);
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

    const rotators = [];

    document.querySelectorAll('.catalog-item[data-kind="producto"] .media').forEach((media) => {
        const current = media.querySelector(':scope > img');
        if (!current) return;

        const rawSrc = current.getAttribute('src') || '';
        const urls = productImages[rawSrc] || productImages[current.src] || [rawSrc];
        const slides = urls.map((src) => ({src, alt: current.alt || ''}));
        const rotator = buildRotator(media, slides);
        if (rotator) rotators.push(rotator);
    });

    document.querySelectorAll('.catalog-item[data-kind="kit"] .media').forEach((media) => {
        const slides = [...media.querySelectorAll('.kit-collage img')].map((image) => ({
            src: image.getAttribute('src') || image.src,
            alt: image.alt || 'Foto del kit',
        }));
        const rotator = buildRotator(media, slides);
        if (rotator) rotators.push(rotator);
    });

    if (reduceMotion) return;

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                entry.target.dataset.visible = entry.isIntersecting ? '1' : '0';
            });
        }, {rootMargin: '120px 0px'});
        rotators.forEach((rotator) => observer.observe(rotator));
    }

    const advance = (rotator) => {
        const slides = [...rotator.querySelectorAll('img')];
        if (slides.length < 2) return;
        const current = Number(rotator.dataset.current || 0);
        const next = (current + 1) % slides.length;
        slides[current]?.classList.remove('is-active');
        slides[next]?.classList.add('is-active');
        rotator.dataset.current = String(next);
    };

    window.setInterval(() => {
        if (document.hidden) return;
        rotators.forEach((rotator) => {
            if (rotator.dataset.visible === '0' || rotator.matches(':hover')) return;
            advance(rotator);
        });
    }, 4400);
})();
</script>
"""


def _product_image_map():
    grouped = defaultdict(list)
    imagenes = (
        ProductoImagen.objects
        .filter(ambiente=entorno_imagenes())
        .order_by('producto_id', 'orden', 'id')
    )
    for imagen in imagenes:
        if len(grouped[imagen.producto_id]) < 2:
            grouped[imagen.producto_id].append(imagen)

    payload = {}
    for grupo in grouped.values():
        if not grupo:
            continue
        principal = next((imagen for imagen in grupo if imagen.orden == 1), grupo[0])
        payload[principal.url] = [imagen.url for imagen in grupo]
    return payload


class CatalogRotatorMiddleware:
    """Convierte las fotos del catálogo en galerías 1:1 rotativas y livianas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        view_name = match.view_name if match else ''

        if (
            view_name not in {'catalogo', 'catalogo_legacy'}
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
            payload = json.dumps(
                _product_image_map(),
                ensure_ascii=False,
            ).replace('</', '<\\/')
            script = CATALOG_ROTATOR_SCRIPT.replace('__PRODUCT_IMAGES__', payload)
            contenido = contenido.replace('</body>', script + '\n</body>', 1)

        encoded = contenido.encode(response.charset or 'utf-8')
        response.content = encoded
        response['Content-Length'] = str(len(encoded))
        return response
