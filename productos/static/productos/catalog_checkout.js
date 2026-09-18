(() => {
    const STORAGE_KEY = 'dv-catalog-cart-v1';
    const summary = document.querySelector('[data-checkout-summary]');
    const totalNode = document.querySelector('[data-checkout-total]');
    const payloadInput = document.getElementById('cart_payload');
    const form = document.getElementById('dv-checkout-form');
    const submit = document.querySelector('[data-checkout-submit]');
    const loader = document.querySelector('[data-checkout-loader]');

    if (!summary || !payloadInput || !form) return;

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
            const selected = (item.selections || []).map((entry) => entry.name).join(' · ');
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
            return '<article class="checkout-line">'
                + '<div><strong>' + item.name + '</strong><span>' + meta + '</span>' + extra + '</div>'
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

    window.setTimeout(render, 220);

    form.addEventListener('submit', (event) => {
        const items = read();
        if (!items.length) {
            event.preventDefault();
            return;
        }

        payloadInput.value = JSON.stringify(minimalPayload(items));

        if (!form.checkValidity()) return;

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
