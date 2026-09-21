(() => {
    const script = document.currentScript;
    if (!script) return;

    const VISITOR_KEY = 'dv-metrics-visitor-v1';
    const SESSION_KEY = 'dv-metrics-session-v1';
    const SESSION_TTL = 30 * 60 * 1000;
    const endpoint = '/metricas/evento/';

    const uuid = () => {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(
            /[xy]/g,
            (char) => {
                const value = Math.random() * 16 | 0;
                const next = char === 'x' ? value : (value & 0x3 | 0x8);
                return next.toString(16);
            },
        );
    };

    const safeStorage = {
        get(key) {
            try { return localStorage.getItem(key); } catch (_) { return null; }
        },
        set(key, value) {
            try { localStorage.setItem(key, value); } catch (_) {}
        },
    };

    let visitorId = safeStorage.get(VISITOR_KEY);
    if (!visitorId) {
        visitorId = uuid();
        safeStorage.set(VISITOR_KEY, visitorId);
    }

    let session = {};
    try {
        session = JSON.parse(safeStorage.get(SESSION_KEY) || '{}');
    } catch (_) {
        session = {};
    }

    const now = Date.now();
    const params = new URLSearchParams(window.location.search);
    const utmRaw = (params.get('utm_source') || '').trim();
    const explicitSource = utmRaw
        ? 'utm:' + utmRaw.toLowerCase().slice(0, 90)
        : '';

    const expired = !session.id || !session.last || now - session.last > SESSION_TTL;
    const sourceChanged = Boolean(
        explicitSource
        && session.source
        && session.source !== explicitSource
    );

    if (expired || sourceChanged || (explicitSource && !session.id)) {
        let source = explicitSource || 'Directo';

        if (!explicitSource && document.referrer) {
            try {
                const ref = new URL(document.referrer);
                if (ref.hostname && ref.hostname !== window.location.hostname) {
                    source = ref.hostname.replace(/^www\./, '');
                }
            } catch (_) {}
        }

        session = {
            id: uuid(),
            last: now,
            source,
        };
    } else {
        session.last = now;
        if (explicitSource) {
            session.source = explicitSource;
        }
    }
    safeStorage.set(SESSION_KEY, JSON.stringify(session));

    const secure = window.location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = 'dv_visitor_id=' + encodeURIComponent(visitorId)
        + '; Max-Age=15552000; Path=/; SameSite=Lax' + secure;
    document.cookie = 'dv_session_id=' + encodeURIComponent(session.id)
        + '; Max-Age=1800; Path=/; SameSite=Lax' + secure;
    document.cookie = 'dv_metric_source=' + encodeURIComponent(session.source || 'Directo')
        + '; Max-Age=1800; Path=/; SameSite=Lax' + secure;

    const send = (evento, extra = {}) => {
        const payload = {
            evento,
            pagina: extra.pagina || script.dataset.pageKind || '',
            contenido_tipo: extra.contenidoTipo || '',
            contenido_id: extra.contenidoId || null,
            ruta: window.location.pathname.slice(0, 255),
            origen: session.source || 'Directo',
        };

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'DV-Metrics',
            },
            body: JSON.stringify(payload),
        }).catch(() => {});
    };

    window.DVMetrics = {
        track(evento, extra = {}) {
            send(String(evento || '').toUpperCase(), extra);
        },
    };

    send('PAGE_VIEW', {
        contenidoTipo: script.dataset.contentKind || '',
        contenidoId: script.dataset.contentId || null,
    });

    document.addEventListener('click', (event) => {
        const checkout = event.target.closest('[data-dv-cart-checkout]');
        if (
            checkout
            && !checkout.classList.contains('is-disabled')
            && checkout.getAttribute('aria-disabled') !== 'true'
        ) {
            send('CHECKOUT_START');
        }
    }, true);
})();
