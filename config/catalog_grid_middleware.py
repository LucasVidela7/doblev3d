from config.catalog_contact_middleware import (
    CONTACT_STYLE,
    _contactos_html,
    _contactos_insertados,
)


CATALOG_GRID_STYLE = r"""
<style id="dv-catalog-grid-density-fix">
/*
 * Cuando un filtro deja pocos resultados, conservamos el ancho habitual de
 * las tarjetas en vez de estirar el único producto a todo el contenedor.
 * auto-fill mantiene las columnas vacías; en móvil seguimos usando una sola.
 */
@media (min-width: 581px) {
    .grid {
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)) !important;
    }
}

@media (min-width: 581px) and (max-width: 900px) {
    .grid {
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)) !important;
    }
}

/* Los filtros sin elementos disponibles no ocupan espacio ni quedan
   accesibles por teclado. El atributo hidden también comunica el estado
   correctamente a lectores de pantalla. */
.filter[hidden],
.categories[hidden],
.segments[hidden] {
    display: none !important;
}
</style>
"""


CATALOG_EMPTY_FILTERS_SCRIPT = r"""
<script id="dv-catalog-empty-filters-script">
(() => {
    const items = [...document.querySelectorAll('.catalog-item')];
    const kindButtons = [...document.querySelectorAll('[data-kind].filter')];
    const categoryButtons = [...document.querySelectorAll('[data-category].filter')];
    const categories = document.querySelector('.categories');
    const segments = document.querySelector('.segments');
    const search = document.getElementById('catalog-search');
    const sections = [...document.querySelectorAll('[data-section]')];

    if (!kindButtons.length) return;

    const normalize = (value) =>
        (value || '')
            .toLocaleLowerCase('es')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .trim();

    const hasKind = (kind) =>
        items.some((item) => item.dataset.kind === kind);

    const activeKind = () =>
        kindButtons.find((button) => button.classList.contains('is-active'))?.dataset.kind || 'all';

    const syncCounts = () => {
        sections.forEach((section) => {
            const countNode = section.querySelector('.count');
            if (!countNode) return;

            const visibleCount = [...section.querySelectorAll('.catalog-item')]
                .filter((item) => !item.classList.contains('hidden-by-filter'))
                .length;

            countNode.textContent = visibleCount === 1
                ? '1 disponible'
                : `${visibleCount} disponibles`;
        });
    };

    const syncEmptyFilters = () => {
        const hasAnyCatalogItem = items.some(
            (item) => item.dataset.kind === 'producto' || item.dataset.kind === 'kit',
        );

        if (segments) {
            segments.hidden = !hasAnyCatalogItem;
        }

        // Productos/Kits sólo aparecen si existe al menos una tarjeta real
        // de ese tipo en el catálogo. "Todo" queda disponible mientras haya
        // al menos un elemento de cualquier tipo.
        kindButtons.forEach((button) => {
            const kind = button.dataset.kind || 'all';
            button.hidden = kind === 'all'
                ? !hasAnyCatalogItem
                : !hasKind(kind);
        });

        let kind = activeKind();
        if (kind !== 'all' && !hasKind(kind)) {
            const allButton = kindButtons.find((button) => button.dataset.kind === 'all');
            if (allButton && !allButton.hidden && !allButton.classList.contains('is-active')) {
                allButton.click();
                return;
            }
            kind = 'all';
        }

        const availableCategories = new Set(
            items
                .filter((item) => kind === 'all' || item.dataset.kind === kind)
                .map((item) => normalize(item.dataset.category))
                .filter(Boolean),
        );

        let activeCategoryHidden = false;
        categoryButtons.forEach((button) => {
            const category = normalize(button.dataset.category);
            const available = !category || availableCategories.has(category);
            button.hidden = !available;
            if (!available && button.classList.contains('is-active')) {
                activeCategoryHidden = true;
            }
        });

        // Si al cambiar de Productos a Kits la categoría seleccionada dejó de
        // tener resultados, volvemos automáticamente a "Todas las categorías".
        if (activeCategoryHidden) {
            const allCategoriesButton = categoryButtons.find(
                (button) => !normalize(button.dataset.category),
            );
            if (allCategoriesButton) {
                allCategoriesButton.click();
                return;
            }
        }

        if (categories) {
            const specificVisible = categoryButtons.some(
                (button) => normalize(button.dataset.category) && !button.hidden,
            );
            categories.hidden = !specificVisible;
        }
    };

    const syncCatalogUi = () => {
        syncEmptyFilters();
        syncCounts();
    };

    const scheduleCatalogUiSync = () => {
        window.setTimeout(syncCatalogUi, 0);
    };

    kindButtons.forEach((button) => {
        button.addEventListener('click', scheduleCatalogUiSync);
    });

    categoryButtons.forEach((button) => {
        button.addEventListener('click', scheduleCatalogUiSync);
    });

    search?.addEventListener('input', scheduleCatalogUiSync);

    syncCatalogUi();
})();
</script>
"""


class CatalogGridMiddleware:
    """Densidad, filtros útiles y accesos de contacto del catálogo público."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        view_name = match.view_name if match else ""

        es_listado = view_name in {"catalogo", "catalogo_legacy"}
        es_detalle_kit = view_name == "catalogo_kit_detalle"

        if (
            not (es_listado or es_detalle_kit)
            or response.status_code != 200
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if es_listado and "dv-catalog-grid-density-fix" not in html and "</head>" in html:
            html = html.replace(
                "</head>",
                CATALOG_GRID_STYLE + "\n</head>",
                1,
            )

        contactos = _contactos_html()
        if contactos:
            if "dv-catalog-contact-style" not in html and "</head>" in html:
                html = html.replace(
                    "</head>",
                    CONTACT_STYLE + "\n</head>",
                    1,
                )

            if not _contactos_insertados(html) and "</header>" in html:
                html = html.replace(
                    "</header>",
                    contactos + "\n</header>",
                    1,
                )

        if es_listado and "dv-catalog-empty-filters-script" not in html and "</body>" in html:
            html = html.replace(
                "</body>",
                CATALOG_EMPTY_FILTERS_SCRIPT + "\n</body>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
