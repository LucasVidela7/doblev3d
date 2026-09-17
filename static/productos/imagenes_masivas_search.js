(() => {
  function init() {
    const queue = document.getElementById('bulk-queue');
    const dataNode = document.getElementById('productos-masivos-data');
    if (!queue || !dataNode || document.getElementById('dv-product-search-list')) return;

    let products = [];
    try { products = JSON.parse(dataNode.textContent || '[]'); } catch (_) { return; }

    const byId = new Map(products.map(p => [String(p.id), p]));
    const labelFor = p => `${p.codigo} · ${p.nombre}`;
    const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

    const list = document.createElement('datalist');
    list.id = 'dv-product-search-list';
    products.forEach(product => {
      const option = document.createElement('option');
      option.value = labelFor(product);
      option.label = `${product.tipo || 'Producto'} · ${(product.imagenes || []).length}/2 fotos`;
      list.appendChild(option);
    });
    document.body.appendChild(list);

    const style = document.createElement('style');
    style.textContent = `.dv-product-search{width:100%;min-height:44px;border:1px solid #d6dbe1;border-radius:10px;background:#fff;padding:8px 10px;font-size:11px;color:#24272b;outline:none}.dv-product-search:focus{border-color:#8aa0ba;box-shadow:0 0 0 3px rgba(72,104,143,.10)}.dv-product-search:disabled{background:#f4f5f7;color:#92979d;cursor:not-allowed}@media(max-width:620px){.dv-product-search{min-height:46px;font-size:12px}}`;
    document.head.appendChild(style);

    const resolveProduct = raw => {
      const term = normalize(raw);
      if (!term) return null;
      const exact = products.find(p => normalize(labelFor(p)) === term)
        || products.find(p => normalize(p.codigo) === term)
        || products.find(p => normalize(p.nombre) === term);
      if (exact) return exact;
      const matches = products.filter(p => normalize(p.codigo).includes(term) || normalize(p.nombre).includes(term) || normalize(labelFor(p)).includes(term));
      return matches.length === 1 ? matches[0] : null;
    };

    function searchify() {
      queue.querySelectorAll('select[data-field="product"]').forEach(select => {
        if (select.dataset.dvSearchified === '1') return;
        select.dataset.dvSearchified = '1';
        select.style.display = 'none';

        const input = document.createElement('input');
        input.type = 'search';
        input.className = 'dv-product-search';
        input.setAttribute('list', 'dv-product-search-list');
        input.setAttribute('autocomplete', 'off');
        input.setAttribute('spellcheck', 'false');
        input.setAttribute('placeholder', 'Buscar por código o nombre…');
        input.setAttribute('aria-label', 'Buscar producto');
        input.disabled = select.disabled;

        const current = byId.get(String(select.value));
        input.value = current ? labelFor(current) : '';

        const commit = () => {
          const product = resolveProduct(input.value);
          if (!product) {
            if (!input.value.trim() && select.value) {
              select.value = '';
              select.dispatchEvent(new Event('change', { bubbles: true }));
            }
            return;
          }
          input.value = labelFor(product);
          if (String(select.value) !== String(product.id)) {
            select.value = String(product.id);
            select.dispatchEvent(new Event('change', { bubbles: true }));
          }
        };

        input.addEventListener('change', commit);
        input.addEventListener('keydown', event => {
          if (event.key === 'Enter') {
            event.preventDefault();
            commit();
            input.blur();
          }
        });
        input.addEventListener('focus', () => input.select());
        select.parentNode.insertBefore(input, select);
      });
    }

    new MutationObserver(searchify).observe(queue, { childList: true, subtree: true });
    searchify();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
