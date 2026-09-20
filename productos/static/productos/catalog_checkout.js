(() => {
    const STORAGE_KEY = 'dv-catalog-cart-v1';
    const summary = document.querySelector('[data-checkout-summary]');
    const totalNode = document.querySelector('[data-checkout-total]');
    const payloadInput = document.getElementById('cart_payload');
    const form = document.getElementById('dv-checkout-form');
    const submit = document.querySelector('[data-checkout-submit]');
    const loader = document.querySelector('[data-checkout-loader]');
    const specialObservation = document.querySelector('[data-special-observation]');
    const observations = document.getElementById('observaciones');

    if (!summary || !payloadInput || !form) return;

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
            const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            return Array.isArray(data) ? data : [];
        } catch (_) {
            return [];
        }
    };

    const minimalPayload = (items) =>
        items.map((item) => ({
            key: [
                item.kind,
                item.id,
                (item.selections || [])
                    .map((entry) => Number(entry.id))
                    .sort((a, b) => a - b)
                    .join(','),
            ].join(':'),
            kind: item.kind,
            id: Number(item.id),
            qty: Number(item.qty || 1),
            selections: (item.selections || []).map((entry) => ({
                id: Number(entry.id),
            })),
        }));

    const render = () => {
        const items = read();
        payloadInput.value = JSON.stringify(minimalPayload(items));

        if (!items.length) {
            summary.innerHTML = '<div class="checkout-empty"><strong>Tu carrito está vacío.</strong><span>Volvé al catálogo para agregar productos o kits.</span></div>';
            totalNode.textContent = money(0);
            submit.disabled = true;
            return;
        }

        summary.innerHTML = items.map((item) => {
            const selected = (item.selections || []).map((entry) => escapeHtml(entry.name)).join(' · ');
            const additional = (item.selections || []).reduce(
                (sum, entry) => sum + Number(entry.extra || 0),
                0,
            );
            const meta = item.kind === 'kit'
                ? (selected || 'Composición fija')
                : 'Producto';
            const extra = additional > 0
                ? '<span class="checkout-extra">+' + money(additional) + ' adicional</span>'
                : '';
            const discount = Number(item.discountPercent || 0);
            const listUnit = Number(item.listUnitPrice ?? item.unitPrice ?? 0);
            const finalUnit = Number(item.unitPrice || 0);
            const savings = Math.max(
                Number(item.savings || 0),
                (listUnit - finalUnit) * Number(item.qty || 1),
            );
            const discountHtml = discount > 0 && savings > 0
                ? '<span class="checkout-discount">'
                    + discount.toLocaleString('es-AR', {maximumFractionDigits: 1})
                    + '% desc. · ahorrás ' + money(savings)
                    + '</span>'
                : '';
            const media = item.image
                ? '<img class="checkout-thumb" src="' + escapeHtml(item.image) + '" alt="">'
                : '<span class="checkout-thumb checkout-thumb--empty">'
                    + escapeHtml(String(item.name || '?').slice(0, 1).toUpperCase())
                    + '</span>';

            return '<article class="checkout-line">'
                + media
                + '<div class="checkout-line-main"><strong>' + escapeHtml(item.name) + '</strong><span>' + meta + '</span>' + extra + discountHtml + '</div>'
                + '<div class="checkout-line-money"><b>' + money(Number(item.unitPrice || 0) * Number(item.qty || 1)) + '</b><span>x ' + item.qty + '</span></div>'
                + '</article>';
        }).join('');

        const total = items.reduce(
            (sum, item) => sum + Number(item.unitPrice || 0) * Number(item.qty || 1),
            0,
        );
        totalNode.textContent = money(total);
        submit.disabled = false;
    };

    specialObservation?.addEventListener('click', () => {
        if (!observations) return;
        const prompt = (
            'Producto que no encontré en el catálogo: '
            + '\nDetalle / referencia: '
            + '\nCantidad aproximada: '
        );
        if (!observations.value.trim()) {
            observations.value = prompt;
        } else if (!observations.value.includes('Producto que no encontré en el catálogo:')) {
            observations.value = observations.value.trim() + '\n\n' + prompt;
        }
        observations.focus();
        observations.setSelectionRange(
            observations.value.length,
            observations.value.length,
        );
    });

    window.setTimeout(render, 220);
    document.addEventListener('dv-cart-change', render);

    form.addEventListener('submit', (event) => {
        const items = read();
        if (!items.length) {
            event.preventDefault();
            return;
        }

        payloadInput.value = JSON.stringify(minimalPayload(items));

        if (!form.checkValidity()) {
            event.preventDefault();
            form.reportValidity();
            return;
        }

        if (loader) {
            loader.classList.add('is-visible');
            loader.setAttribute('aria-hidden', 'false');
        }
        submit.disabled = true;
        submit.innerHTML = '<span class="checkout-submit-spinner" aria-hidden="true"></span><span>ENVIANDO</span>';
    });

    window.addEventListener('pageshow', () => {
        if (loader) {
            loader.classList.remove('is-visible');
            loader.setAttribute('aria-hidden', 'true');
        }
        render();
    });
})();
