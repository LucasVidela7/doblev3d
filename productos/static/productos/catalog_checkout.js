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
    const volumeModal = document.querySelector('[data-limit-modal]');
    const volumeClose = volumeModal?.querySelectorAll('[data-limit-modal-close], [data-limit-continue], [data-limit-edit-cart]') || [];
    let volumeNoticeDismissed = false;

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

    const signature = (item) => {
        const selected = (item.selections || [])
            .map((entry) => Number(entry.id))
            .sort((a, b) => a - b)
            .join(',');
        const base = [item.kind, item.id, selected].join(':');
        const color = String(item.color || '').trim();
        if (item.colorMode === 'ESPECIFICO') {
            return base + ':color:'
                + encodeURIComponent(
                    color
                        ? color.toLocaleLowerCase('es-AR')
                        : '__pending__',
                );
        }
        return base;
    };

    const minimalPayload = (items) =>
        items.map((item) => ({
            key: signature(item),
            kind: item.kind,
            id: Number(item.id),
            qty: Number(item.qty || 1),
            color_mode: item.colorMode || '',
            color: item.color || '',
            selections: (item.selections || []).map((entry) => ({
                id: Number(entry.id),
            })),
        }));

    const hideVolumeModal = () => {
        if (!volumeModal) return;
        volumeModal.hidden = true;
        volumeModal.setAttribute('aria-hidden', 'true');
        volumeNoticeDismissed = true;
    };

    const syncVolumeNotice = (items) => {
        if (!volumeModal) return;
        const units = items.reduce(
            (sum, item) => sum + Number(item.qty || 0),
            0,
        );

        if (units <= 100) {
            volumeNoticeDismissed = false;
            volumeModal.hidden = true;
            volumeModal.setAttribute('aria-hidden', 'true');
            return;
        }

        if (volumeNoticeDismissed) return;

        volumeModal.hidden = false;
        volumeModal.setAttribute('aria-hidden', 'false');
    };

    volumeClose.forEach((button) => {
        button.addEventListener('click', hideVolumeModal);
    });

    volumeModal?.addEventListener('click', (event) => {
        if (event.target === volumeModal) hideVolumeModal();
    });

    document.addEventListener('keydown', (event) => {
        if (
            event.key === 'Escape'
            && volumeModal
            && !volumeModal.hidden
        ) {
            hideVolumeModal();
        }
    });

    const render = () => {
        const items = read();
        payloadInput.value = JSON.stringify(minimalPayload(items));
        syncVolumeNotice(items);

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
            const colorMeta = item.colorEnabled || item.colorMode
                ? (
                    item.colorMode === 'ESPECIFICO' && item.color
                        ? 'Color: ' + escapeHtml(item.color)
                        : 'Colores surtidos'
                )
                : '';
            const baseMeta = item.kind === 'kit'
                ? (selected || 'Composición fija')
                : 'Producto';
            const meta = colorMeta
                ? baseMeta + ' · ' + colorMeta
                : baseMeta;
            const optionExtra = additional > 0
                ? '<span class="checkout-extra">+' + money(additional) + ' por opciones</span>'
                : '';
            const colorSurcharge = Number(item.colorSurcharge || 0);
            const colorExtra = colorSurcharge > 0
                ? '<span class="checkout-extra">+' + money(colorSurcharge) + ' por mismo color</span>'
                : '';
            const extra = optionExtra + colorExtra;
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
