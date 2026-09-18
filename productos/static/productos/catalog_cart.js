(() => {
    const STORAGE_KEY = 'dv-catalog-cart-v1';
    const root = document.querySelector('[data-dv-cart-root]');
    if (!root) return;

    const drawer = root.querySelector('[data-dv-cart-drawer]');
    const overlay = root.querySelector('[data-dv-cart-overlay]');
    const body = root.querySelector('[data-dv-cart-body]');
    const totalNode = root.querySelector('[data-dv-cart-total]');
    const countNodes = [...document.querySelectorAll('[data-dv-cart-count]')];
    const checkout = root.querySelector('[data-dv-cart-checkout]');
    const toast = root.querySelector('[data-dv-cart-toast]');
    let loadingTimer = null;

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

    const write = (items) => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
        syncCount(items);
        document.dispatchEvent(new CustomEvent('dv-cart-change', { detail: items }));
    };

    const signature = (item) => {
        const selected = (item.selections || [])
            .map((entry) => Number(entry.id))
            .sort((a, b) => a - b)
            .join(',');
        return [item.kind, item.id, selected].join(':');
    };

    const syncCount = (items = read()) => {
        const count = items.reduce((sum, item) => sum + Number(item.qty || 0), 0);
        countNodes.forEach((node) => { node.textContent = String(count); });
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
        const original = button.dataset.originalText || button.textContent.trim();
        button.dataset.originalText = original;
        button.classList.add('is-loading');
        button.disabled = true;
        button.innerHTML = '<span class="dv-cart-button-spinner" aria-hidden="true"></span><span>AGREGANDO</span>';
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
        const key = signature(incoming);
        const current = items.find((item) => signature(item) === key);

        if (current) {
            current.qty = Math.min(20, Number(current.qty || 0) + Number(incoming.qty || 1));
        } else {
            items.push({ ...incoming, qty: Math.min(20, Number(incoming.qty || 1)) });
        }

        write(items);
        buttonLoading(button);
        showToast('Agregado al carrito');
    };

    const skeleton = () => {
        body.innerHTML = '<div class="dv-cart-skeleton"><div class="dv-cart-skeleton-row"></div><div class="dv-cart-skeleton-row"></div><div class="dv-cart-skeleton-row"></div></div>';
    };

    const itemMeta = (item) => {
        if (item.kind !== 'kit') return 'Producto';
        const selections = item.selections || [];
        if (!selections.length) return 'Kit de composición fija';
        const names = selections.map((entry) => escapeHtml(entry.name)).join(' · ');
        const extra = selections.reduce((sum, entry) => sum + Number(entry.extra || 0), 0);
        return extra > 0
            ? names + ' · <b>+' + money(extra) + ' adicional</b>'
            : names;
    };

    const render = () => {
        const items = read();
        syncCount(items);

        if (!items.length) {
            body.innerHTML = '<div class="dv-cart-empty"><div class="dv-cart-empty-icon"><svg viewBox="0 0 24 24"><path d="M3 4h2l2.2 10h10.6L20 7H7"></path><circle cx="9" cy="19" r="1.6"></circle><circle cx="17" cy="19" r="1.6"></circle></svg></div><strong>Tu carrito está vacío</strong><p>Agregá productos o configurá un kit para comenzar.</p></div>';
            totalNode.textContent = money(0);
            checkout.classList.add('is-disabled');
            checkout.setAttribute('aria-disabled', 'true');
            return;
        }

        body.innerHTML = '<div class="dv-cart-items">' + items.map((item) => {
            const subtotal = Number(item.unitPrice || 0) * Number(item.qty || 0);
            const media = item.image
                ? '<img src="' + escapeHtml(item.image) + '" alt="">'
                : '<span>' + escapeHtml(String(item.name || '?').slice(0, 1).toUpperCase()) + '</span>';
            return '<article class="dv-cart-item" data-cart-key="' + signature(item) + '">'
                + '<div class="dv-cart-item-media">' + media + '</div>'
                + '<div class="dv-cart-item-main">'
                + '<div class="dv-cart-item-row"><div class="dv-cart-item-name">' + escapeHtml(item.name) + '</div>'
                + '<button class="dv-cart-item-remove" type="button" data-cart-remove aria-label="Quitar">×</button></div>'
                + '<div class="dv-cart-item-meta">' + itemMeta(item) + '</div>'
                + '<div class="dv-cart-item-bottom">'
                + '<div class="dv-cart-stepper"><button type="button" data-cart-minus>−</button><span>' + item.qty + '</span><button type="button" data-cart-plus>+</button></div>'
                + '<div class="dv-cart-item-price"><strong>' + money(subtotal) + '</strong><span>' + money(item.unitPrice) + ' c/u</span></div>'
                + '</div></div></article>';
        }).join('') + '</div>';

        const total = items.reduce(
            (sum, item) => sum + Number(item.unitPrice || 0) * Number(item.qty || 0),
            0,
        );
        totalNode.textContent = money(total);
        checkout.classList.remove('is-disabled');
        checkout.removeAttribute('aria-disabled');
    };

    const open = () => {
        document.documentElement.classList.add('dv-cart-open');
        skeleton();
        window.clearTimeout(loadingTimer);
        loadingTimer = window.setTimeout(render, 180);
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

        const productButton = event.target.closest('[data-dv-cart-product]');
        if (productButton) {
            addItem({
                kind: 'product',
                id: Number(productButton.dataset.productId),
                name: productButton.dataset.productName || 'Producto',
                qty: 1,
                unitPrice: Number(productButton.dataset.productPrice || 0),
                image: productButton.dataset.productImage || '',
                selections: [],
            }, productButton);
            return;
        }

        const row = event.target.closest('[data-cart-key]');
        if (!row) return;

        const items = read();
        const key = row.dataset.cartKey;
        const index = items.findIndex((item) => signature(item) === key);
        if (index < 0) return;

        if (event.target.closest('[data-cart-remove]')) {
            items.splice(index, 1);
            write(items);
            render();
            return;
        }

        if (event.target.closest('[data-cart-minus]')) {
            items[index].qty = Number(items[index].qty || 1) - 1;
            if (items[index].qty <= 0) items.splice(index, 1);
            write(items);
            render();
            return;
        }

        if (event.target.closest('[data-cart-plus]')) {
            items[index].qty = Math.min(20, Number(items[index].qty || 1) + 1);
            write(items);
            render();
        }
    });

    overlay?.addEventListener('click', close);
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') close();
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
        const options = [...document.querySelectorAll('[data-dv-kit-option]')];

        const optionCount = (node) => Number(node.dataset.count || 0);

        const updateKit = () => {
            const selected = options.reduce((sum, node) => sum + optionCount(node), 0);
            const extras = options.reduce(
                (sum, node) => sum + optionCount(node) * Number(node.dataset.extra || 0),
                0,
            );
            const qty = Math.max(1, Math.min(20, Number(qtyInput?.value || 1)));
            if (qtyInput) qtyInput.value = String(qty);
            const unit = base + extras;
            if (priceNode) priceNode.textContent = money(unit * qty);

            if (status) {
                status.textContent = mode === 'LIBRE_CATEGORIA'
                    ? selected + ' de ' + required + ' seleccionados'
                    : 'Composición fija';
            }

            if (addButton) {
                addButton.disabled = mode === 'LIBRE_CATEGORIA' && selected !== required;
            }

            options.forEach((node) => {
                const count = optionCount(node);
                node.classList.toggle('is-selected', count > 0);
                const counter = node.querySelector('[data-kit-option-count]');
                if (counter) counter.textContent = String(count);
            });
        };

        document.addEventListener('click', (event) => {
            const plus = event.target.closest('[data-kit-option-plus]');
            const minus = event.target.closest('[data-kit-option-minus]');
            const node = event.target.closest('[data-dv-kit-option]');
            if (!node || (!plus && !minus)) return;

            const current = optionCount(node);
            const selected = options.reduce((sum, item) => sum + optionCount(item), 0);

            if (plus && selected < required) node.dataset.count = String(current + 1);
            if (minus && current > 0) node.dataset.count = String(current - 1);
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
                        name: node.dataset.productName || 'Producto',
                        extra: Number(node.dataset.extra || 0),
                    });
                }
            });

            if (mode === 'LIBRE_CATEGORIA' && selections.length !== required) {
                showToast('Completá la selección del kit');
                return;
            }

            const unitPrice = base + selections.reduce(
                (sum, item) => sum + Number(item.extra || 0),
                0,
            );

            addItem({
                kind: 'kit',
                id: Number(config.dataset.kitId),
                name: config.dataset.kitName || 'Kit',
                qty: Math.max(1, Math.min(20, Number(qtyInput?.value || 1))),
                unitPrice,
                basePrice: base,
                image: config.dataset.image || '',
                selections,
            }, addButton);
        });

        updateKit();
    }

    syncCount();
    window.DVCart = { read, write, open, addItem, money, storageKey: STORAGE_KEY };
})();
