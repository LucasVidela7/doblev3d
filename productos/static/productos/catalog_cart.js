(() => {
    const STORAGE_KEY = 'dv-catalog-cart-v1';
    const root = document.querySelector('[data-dv-cart-root]');
    if (!root) return;

    const pricingUrl = root.dataset.pricingUrl || '';
    const fab = root.querySelector('[data-dv-cart-open]');
    const drawer = root.querySelector('[data-dv-cart-drawer]');
    const overlay = root.querySelector('[data-dv-cart-overlay]');
    const body = root.querySelector('[data-dv-cart-body]');
    const totalNode = root.querySelector('[data-dv-cart-total]');
    const savingNode = root.querySelector('[data-dv-cart-saving]');
    const countNodes = [...document.querySelectorAll('[data-dv-cart-count]')];
    const checkout = root.querySelector('[data-dv-cart-checkout]');
    const toast = root.querySelector('[data-dv-cart-toast]');

    let loadingTimer = null;
    let pricingTimer = null;
    let pricingSequence = 0;

    const escapeHtml = (value) =>
        String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;',
        }[char]));

    const money = (value) =>
        new Intl.NumberFormat('es-AR', {
            style: 'currency',
            currency: 'ARS',
            maximumFractionDigits: 0,
        }).format(Number(value || 0));

    const read = () => {
        try {
            const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            return Array.isArray(value) ? value : [];
        } catch (_) {
            return [];
        }
    };

    const signature = (item) => {
        const selected = (item.selections || [])
            .map((entry) => Number(entry.id))
            .sort((a, b) => a - b)
            .join(',');
        return [item.kind, item.id, selected].join(':');
    };

    const payloadFor = (items) =>
        items.map((item) => ({
            key: signature(item),
            kind: item.kind,
            id: Number(item.id),
            qty: Number(item.qty || 1),
            selections: (item.selections || []).map((entry) => ({
                id: Number(entry.id),
            })),
        }));

    const syncCount = (items = read()) => {
        const count = items.reduce(
            (sum, item) => sum + Number(item.qty || 0),
            0,
        );
        countNodes.forEach((node) => {
            node.textContent = String(count);
        });
    };

    const setRaw = (items) => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
        syncCount(items);
        document.dispatchEvent(
            new CustomEvent('dv-cart-change', { detail: items }),
        );
    };

    const resetLinePricing = (item) => {
        const listPrice = Number(
            item.listUnitPrice ?? item.unitPrice ?? 0,
        );
        item.listUnitPrice = listPrice;
        item.unitPrice = listPrice;
        item.discountPercent = 0;
        item.savings = 0;
    };

    const write = (items, recalculate = true) => {
        setRaw(items);
        if (recalculate) schedulePricing();
    };

    const showToast = (message) => {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add('is-show');
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(
            () => toast.classList.remove('is-show'),
            1800,
        );
    };

    const buttonLoading = (button, successText = 'AGREGADO ✓') => {
        if (!button) return;
        const original =
            button.dataset.originalText || button.textContent.trim();
        button.dataset.originalText = original;
        button.classList.add('is-loading');
        button.disabled = true;
        button.innerHTML =
            '<span class="dv-cart-button-spinner" aria-hidden="true"></span>'
            + '<span>AGREGANDO</span>';

        window.setTimeout(() => {
            button.classList.remove('is-loading');
            button.innerHTML = successText;
            window.setTimeout(() => {
                button.disabled = false;
                button.textContent = original;
            }, 700);
        }, 330);
    };

    const addItem = (incoming, button) => {
        const items = read();
        incoming.listUnitPrice = Number(
            incoming.listUnitPrice ?? incoming.unitPrice ?? 0,
        );
        incoming.unitPrice = incoming.listUnitPrice;
        incoming.discountPercent = 0;
        incoming.savings = 0;

        const key = signature(incoming);
        const current = items.find(
            (item) => signature(item) === key,
        );

        if (current) {
            current.qty = Math.min(
                20,
                Number(current.qty || 0) + Number(incoming.qty || 1),
            );
            if (!current.listUnitPrice) {
                current.listUnitPrice = incoming.listUnitPrice;
            }
            resetLinePricing(current);
        } else {
            items.push({
                ...incoming,
                qty: Math.min(20, Number(incoming.qty || 1)),
            });
        }

        write(items);
        render();
        buttonLoading(button);
        showToast('Agregado al carrito');
    };

    const skeleton = () => {
        if (!body) return;
        body.innerHTML =
            '<div class="dv-cart-skeleton">'
            + '<div class="dv-cart-skeleton-row"></div>'
            + '<div class="dv-cart-skeleton-row"></div>'
            + '<div class="dv-cart-skeleton-row"></div>'
            + '</div>';
    };

    const itemMeta = (item) => {
        if (item.kind !== 'kit') return 'Producto';

        const selections = item.selections || [];
        if (!selections.length) return 'Kit de composición fija';

        const names = selections
            .map((entry) => escapeHtml(entry.name))
            .join(' · ');

        const extra = selections.reduce(
            (sum, entry) => sum + Number(entry.extra || 0),
            0,
        );

        return extra > 0
            ? names + ' · <b>+' + money(extra) + ' adicional</b>'
            : names;
    };

    const render = () => {
        if (!body || !totalNode || !checkout) return;

        const items = read();
        syncCount(items);

        if (!items.length) {
            body.innerHTML =
                '<div class="dv-cart-empty">'
                + '<div class="dv-cart-empty-icon">'
                + '<svg viewBox="0 0 24 24"><path d="M3 4h2l2.2 10h10.6L20 7H7"></path>'
                + '<circle cx="9" cy="19" r="1.6"></circle>'
                + '<circle cx="17" cy="19" r="1.6"></circle></svg>'
                + '</div><strong>Tu carrito está vacío</strong>'
                + '<p>Agregá productos o configurá un kit para comenzar.</p>'
                + '</div>';
            totalNode.textContent = money(0);
            checkout.classList.add('is-disabled');
            checkout.setAttribute('aria-disabled', 'true');
            if (savingNode) savingNode.hidden = true;
            return;
        }

        body.innerHTML =
            '<div class="dv-cart-items">'
            + items.map((item) => {
                const qty = Number(item.qty || 0);
                const unit = Number(item.unitPrice || 0);
                const listUnit = Number(
                    item.listUnitPrice ?? unit,
                );
                const subtotal = unit * qty;
                const listSubtotal = listUnit * qty;
                const savings = Math.max(
                    Number(item.savings || 0),
                    listSubtotal - subtotal,
                );
                const discount = Number(item.discountPercent || 0);

                const media = item.image
                    ? '<img src="' + escapeHtml(item.image) + '" alt="">'
                    : '<span>'
                        + escapeHtml(
                            String(item.name || '?')
                                .slice(0, 1)
                                .toUpperCase(),
                        )
                        + '</span>';

                const discountHtml = discount > 0 && savings > 0
                    ? '<span class="dv-cart-discount">'
                        + discount.toLocaleString('es-AR', {
                            maximumFractionDigits: 1,
                        })
                        + '% desc. · ahorrás '
                        + money(savings)
                        + '</span>'
                    : '';

                return '<article class="dv-cart-item" data-cart-key="'
                    + escapeHtml(signature(item))
                    + '">'
                    + '<div class="dv-cart-item-media">' + media + '</div>'
                    + '<div class="dv-cart-item-main">'
                    + '<div class="dv-cart-item-row">'
                    + '<div class="dv-cart-item-name">'
                    + escapeHtml(item.name)
                    + '</div>'
                    + '<button class="dv-cart-item-remove" type="button" '
                    + 'data-cart-remove aria-label="Quitar">×</button>'
                    + '</div>'
                    + '<div class="dv-cart-item-meta">'
                    + itemMeta(item)
                    + discountHtml
                    + '</div>'
                    + '<div class="dv-cart-item-bottom">'
                    + '<div class="dv-cart-stepper">'
                    + '<button type="button" data-cart-minus>−</button>'
                    + '<span>' + qty + '</span>'
                    + '<button type="button" data-cart-plus>+</button>'
                    + '</div>'
                    + '<div class="dv-cart-item-price">'
                    + '<strong>' + money(subtotal) + '</strong>'
                    + '<span>' + money(unit) + ' c/u</span>'
                    + '</div></div></div></article>';
            }).join('')
            + '</div>';

        const total = items.reduce(
            (sum, item) =>
                sum
                + Number(item.unitPrice || 0)
                * Number(item.qty || 0),
            0,
        );

        const listTotal = items.reduce(
            (sum, item) =>
                sum
                + Number(
                    item.listUnitPrice ?? item.unitPrice ?? 0,
                )
                * Number(item.qty || 0),
            0,
        );

        const savings = Math.max(listTotal - total, 0);

        totalNode.textContent = money(total);
        checkout.classList.remove('is-disabled');
        checkout.removeAttribute('aria-disabled');

        if (savingNode) {
            savingNode.hidden = savings <= 0;
            savingNode.textContent =
                savings > 0
                    ? 'Ahorrás ' + money(savings) + ' por cantidad'
                    : '';
        }
    };

    const applyPricingResult = (data) => {
        if (!data?.ok || !Array.isArray(data.lineas)) return;

        const current = read();
        const prices = new Map(
            data.lineas.map((line) => [String(line.key), line]),
        );

        current.forEach((item) => {
            const line = prices.get(signature(item));
            if (!line) return;

            item.listUnitPrice = Number(
                line.precio_lista_unitario || 0,
            );
            item.unitPrice = Number(line.precio_unitario || 0);
            item.discountPercent = Number(
                line.descuento_porcentaje || 0,
            );
            item.savings = Number(line.ahorro || 0);
        });

        setRaw(current);
        render();
    };

    const refreshPricing = async () => {
        if (!pricingUrl) return;

        const items = read();
        if (!items.length) {
            render();
            return;
        }

        const sequence = ++pricingSequence;

        try {
            const response = await fetch(pricingUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify(payloadFor(items)),
            });

            const data = await response.json();
            if (sequence !== pricingSequence) return;

            if (!response.ok || !data.ok) {
                throw new Error(
                    data.mensaje || 'No pudimos actualizar los precios.',
                );
            }

            applyPricingResult(data);
        } catch (_) {
            if (sequence !== pricingSequence) return;
            render();
        }
    };

    function schedulePricing(delay = 120) {
        window.clearTimeout(pricingTimer);
        pricingTimer = window.setTimeout(refreshPricing, delay);
    }

    const open = () => {
        document.documentElement.classList.add('dv-cart-open');
        skeleton();
        window.clearTimeout(loadingTimer);
        loadingTimer = window.setTimeout(render, 180);
        schedulePricing(20);
    };

    const close = () => {
        document.documentElement.classList.remove('dv-cart-open');
    };

    document.addEventListener('click', (event) => {
        const opener = event.target.closest('[data-dv-cart-open]');
        if (opener) {
            event.preventDefault();
            open();
            return;
        }

        if (event.target.closest('[data-dv-cart-close]')) {
            close();
            return;
        }

        const productButton = event.target.closest(
            '[data-dv-cart-product]',
        );
        if (productButton) {
            const listPrice = Number(
                productButton.dataset.productPrice || 0,
            );
            addItem({
                kind: 'product',
                id: Number(productButton.dataset.productId),
                name:
                    productButton.dataset.productName
                    || 'Producto',
                qty: 1,
                unitPrice: listPrice,
                listUnitPrice: listPrice,
                image: productButton.dataset.productImage || '',
                selections: [],
            }, productButton);
            return;
        }

        const row = event.target.closest('[data-cart-key]');
        if (!row) return;

        const items = read();
        const key = row.dataset.cartKey;
        const index = items.findIndex(
            (item) => signature(item) === key,
        );
        if (index < 0) return;

        if (event.target.closest('[data-cart-remove]')) {
            items.splice(index, 1);
            write(items);
            render();
            return;
        }

        if (event.target.closest('[data-cart-minus]')) {
            items[index].qty = Number(items[index].qty || 1) - 1;
            if (items[index].qty <= 0) {
                items.splice(index, 1);
            } else {
                resetLinePricing(items[index]);
            }
            write(items);
            render();
            return;
        }

        if (event.target.closest('[data-cart-plus]')) {
            items[index].qty = Math.min(
                20,
                Number(items[index].qty || 1) + 1,
            );
            resetLinePricing(items[index]);
            write(items);
            render();
        }
    });

    overlay?.addEventListener('click', close);

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') close();
    });

    window.addEventListener('storage', (event) => {
        if (event.key !== STORAGE_KEY) return;
        syncCount();
        render();
        schedulePricing(80);
    });

    const config = document.querySelector('[data-dv-kit-config]');
    if (config) {
        const required = Number(config.dataset.required || 0);
        const mode = config.dataset.mode || 'FIJO';
        const base = Number(config.dataset.basePrice || 0);
        const qtyInput = config.querySelector('[data-dv-kit-qty]');
        const status = config.querySelector('[data-dv-kit-status]');
        const priceNode = config.querySelector('[data-dv-kit-total]');
        const addButton = config.querySelector('[data-dv-kit-add]');
        const options = [
            ...document.querySelectorAll('[data-dv-kit-option]'),
        ];

        const optionCount = (node) =>
            Number(node.dataset.count || 0);

        const updateKit = () => {
            const selected = options.reduce(
                (sum, node) => sum + optionCount(node),
                0,
            );
            const extras = options.reduce(
                (sum, node) =>
                    sum
                    + optionCount(node)
                    * Number(node.dataset.extra || 0),
                0,
            );
            const qty = Math.max(
                1,
                Math.min(20, Number(qtyInput?.value || 1)),
            );
            if (qtyInput) qtyInput.value = String(qty);

            const unitListPrice = base + extras;
            if (priceNode) {
                priceNode.textContent = money(unitListPrice * qty);
            }

            if (status) {
                status.textContent = mode === 'LIBRE_CATEGORIA'
                    ? selected + ' de ' + required + ' seleccionados'
                    : 'Composición fija';
            }

            if (addButton) {
                addButton.disabled =
                    mode === 'LIBRE_CATEGORIA'
                    && selected !== required;
            }

            options.forEach((node) => {
                const count = optionCount(node);
                node.classList.toggle(
                    'is-selected',
                    count > 0,
                );
                const counter = node.querySelector(
                    '[data-kit-option-count]',
                );
                if (counter) counter.textContent = String(count);
            });
        };

        document.addEventListener('click', (event) => {
            const plus = event.target.closest(
                '[data-kit-option-plus]',
            );
            const minus = event.target.closest(
                '[data-kit-option-minus]',
            );
            const node = event.target.closest(
                '[data-dv-kit-option]',
            );
            if (!node || (!plus && !minus)) return;

            const current = optionCount(node);
            const selected = options.reduce(
                (sum, item) => sum + optionCount(item),
                0,
            );

            if (plus && selected < required) {
                node.dataset.count = String(current + 1);
            }
            if (minus && current > 0) {
                node.dataset.count = String(current - 1);
            }
            updateKit();
        });

        qtyInput?.addEventListener('input', updateKit);

        addButton?.addEventListener('click', () => {
            const selections = [];

            options.forEach((node) => {
                const count = optionCount(node);
                for (let i = 0; i < count; i += 1) {
                    selections.push({
                        id: Number(node.dataset.productId),
                        name:
                            node.dataset.productName
                            || 'Producto',
                        extra: Number(node.dataset.extra || 0),
                    });
                }
            });

            if (
                mode === 'LIBRE_CATEGORIA'
                && selections.length !== required
            ) {
                showToast('Completá la selección del kit');
                return;
            }

            const listUnitPrice =
                base
                + selections.reduce(
                    (sum, item) =>
                        sum + Number(item.extra || 0),
                    0,
                );

            addItem({
                kind: 'kit',
                id: Number(config.dataset.kitId),
                name: config.dataset.kitName || 'Kit',
                qty: Math.max(
                    1,
                    Math.min(
                        20,
                        Number(qtyInput?.value || 1),
                    ),
                ),
                unitPrice: listUnitPrice,
                listUnitPrice,
                basePrice: base,
                image: config.dataset.image || '',
                selections,
            }, addButton);
        });

        updateKit();
    }

    syncCount();
    render();
    schedulePricing(260);

    if (fab) {
        window.setTimeout(() => {
            fab.classList.add('is-compact');
        }, 2600);
    }

    window.DVCart = {
        read,
        write,
        open,
        addItem,
        money,
        refreshPricing,
        storageKey: STORAGE_KEY,
    };
})();
