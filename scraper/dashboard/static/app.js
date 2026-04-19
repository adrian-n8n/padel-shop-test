/* ── Estado global ─────────────────────────────────────────────────────────── */
const state = {
  products:          [],   // scraped JSON
  shopifyHandles:    new Set(),
  shopifyBarcodes:   {},   // handle → barcode/EAN
  selected:          new Set(),
  filteredSlugs:     [],
  shopifyStore:      '',
  shopifyConfigured: false,
};

/* ── Helpers DOM ──────────────────────────────────────────────────────────── */
const $  = id  => document.getElementById(id);
const el = sel => document.querySelector(sel);

function log(msg, type = "plain") {
  const box  = $("log-box");
  const line = document.createElement("div");
  const ts   = new Date().toLocaleTimeString("es-ES", { hour12: false });
  line.innerHTML = `<span style="color:#444">[${ts}]</span> <span class="log-${type}">${escHtml(msg)}</span>`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function setMsg(id, text, type = "") {
  const el = $(id);
  el.textContent = text;
  el.className = "msg " + type;
}

/* ── Config ───────────────────────────────────────────────────────────────── */
async function loadConfig() {
  try {
    const cfg = await fetch("/api/config").then(r => r.json());
    $("cfg-store").value = cfg.store || "";
    $("cfg-token").value = cfg.token || "";
    state.shopifyStore      = cfg.store || '';
    state.shopifyConfigured = cfg.configured || false;
    updateShopifyBadge(cfg.configured);
    if (cfg.configured) { loadShopifyHandles(); loadTags(); }
  } catch(e) {
    log("Error cargando config: " + e.message, "err");
  }
}

function updateShopifyBadge(ok) {
  const b = $("shopify-badge");
  b.textContent = ok ? "Shopify: conectado" : "Shopify: no configurado";
  b.className   = "badge " + (ok ? "badge-green" : "badge-grey");
}

$("config-form").addEventListener("submit", async e => {
  e.preventDefault();
  const store = $("cfg-store").value.trim();
  const token = $("cfg-token").value.trim();
  if (!store || !token) { setMsg("config-msg", "Rellena los dos campos", "err"); return; }

  const btn = $("save-config-btn");
  btn.disabled = true; btn.textContent = "Guardando…";
  try {
    const r = await fetch("/api/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ store, token }),
    }).then(r => r.json());
    if (r.ok) {
      setMsg("config-msg", "✓ Guardado", "ok");
      updateShopifyBadge(true);
      log("Credenciales Shopify guardadas", "ok");
      loadShopifyHandles();
    } else {
      setMsg("config-msg", r.error || "Error", "err");
    }
  } catch(e) {
    setMsg("config-msg", e.message, "err");
  } finally {
    btn.disabled = false; btn.textContent = "Guardar configuración";
  }
});

$("toggle-token").addEventListener("click", () => {
  const inp = $("cfg-token");
  inp.type = inp.type === "password" ? "text" : "password";
});

$("refresh-token-btn").addEventListener("click", async () => {
  const btn = $("refresh-token-btn");
  btn.disabled = true; btn.textContent = "Renovando…";
  try {
    const r = await fetch("/api/shopify/refresh-token", { method: "POST" }).then(r => r.json());
    if (r.ok) {
      setMsg("config-msg", `✓ Token renovado: ${r.token}`, "ok");
      updateShopifyBadge(true);
      log("Token Shopify renovado automáticamente", "ok");
      await loadConfig();
      loadTags();
    } else {
      setMsg("config-msg", "Error: " + (r.error || "desconocido"), "err");
      log("Error renovando token: " + r.error, "err");
    }
  } catch(e) {
    setMsg("config-msg", e.message, "err");
  } finally {
    btn.disabled = false; btn.textContent = "🔄 Renovar token automáticamente";
  }
});

/* ── Cargar handles de Shopify ───────────────────────────────────────────── */
async function loadShopifyHandles() {
  log("Consultando productos en Shopify…", "info");
  try {
    const data = await fetch("/api/products/shopify").then(r => r.json());
    if (data.error) { log("Shopify: " + data.error, "err"); return; }
    state.shopifyHandles  = new Set(data.handles);
    state.shopifyBarcodes = data.barcodes || {};
    log(`Shopify: ${data.total} productos en la tienda`, "ok");
    if (state.products.length) renderTable(state.products);
  } catch(e) {
    log("Error Shopify: " + e.message, "err");
  }
}

/* ── Cargar todos los productos de Shopify ──────────────────────────────── */
async function loadAllShopifyProducts() {
  const btn = $("load-shopify-all-btn");
  btn.disabled = true;
  btn.textContent = "Cargando…";
  setMsg("load-shopify-msg", "", "");
  log("Cargando todos los productos de Shopify…", "info");
  try {
    const data = await fetch("/api/products/shopify-all").then(r => r.json());
    if (data.error) { log("Error: " + data.error, "err"); setMsg("load-shopify-msg", data.error, "err"); return; }
    // Guardar handles/barcodes del resultado
    state.shopifyHandles  = new Set(data.products.map(p => p.slug));
    state.shopifyBarcodes = {};
    data.products.forEach(p => { if (p.ean) state.shopifyBarcodes[p.slug] = p.ean; });
    state.products = data.products;
    $('scrape-badge').textContent = `${data.total} productos (Shopify)`;
    $('scrape-badge').className = 'badge badge-green';
    log(`Shopify: ${data.total} productos cargados`, "ok");
    setMsg("load-shopify-msg", `✓ ${data.total} productos`, "ok");
    renderTable(state.products);
    updateStats();
  } catch(e) {
    log("Error cargando Shopify: " + e.message, "err");
    setMsg("load-shopify-msg", e.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "📦 Cargar todos los productos";
  }
}

$("load-shopify-all-btn").addEventListener("click", loadAllShopifyProducts);

/* ── Scraping ─────────────────────────────────────────────────────────────── */
$('scrape-btn').addEventListener('click', async () => {
  const cats  = [...document.querySelectorAll("#cat-group input:checked")].map(i => i.value);
  const pages = parseInt($("pages-input").value) || 3;
  if (!cats.length) { log("Selecciona al menos una categoría", "warn"); return; }

  $("scrape-btn").disabled = true;
  $("scrape-progress").classList.remove("hidden");
  $("scrape-bar").style.width = "0%";
  $("scrape-progress-label").textContent = "Iniciando…";
  $("scrape-badge").textContent = "Scraping en curso…";
  $("scrape-badge").className = "badge badge-yellow";
  log(`Iniciando scraping: [${cats.join(", ")}] · ${pages} páginas`, "info");

  try {
    await fetch("/api/scrape", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ categories: cats, pages }),
    });
  } catch(e) {
    log("Error iniciando scraping: " + e.message, "err");
    $("scrape-btn").disabled = false;
    return;
  }

  const evts = new EventSource("/api/scrape/stream");
  let done = 0;

  evts.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "ping") return;
    if (msg.type === "log")  { log(msg.msg); return; }

    if (msg.type === "progress") {
      done++;
      const pct = Math.min((done / cats.length) * 100, 90);
      $("scrape-bar").style.width = pct + "%";
      $("scrape-progress-label").textContent = `Categoría ${done}/${cats.length} · ${msg.count} productos`;
    }

    if (msg.type === "done") {
      evts.close();
      $("scrape-bar").style.width = "100%";
      $("scrape-progress-label").textContent = `✓ ${msg.total} productos`;
      $("scrape-btn").disabled = false;
      $("scrape-badge").textContent = `${msg.total} productos`;
      $("scrape-badge").className = "badge badge-blue";
      log(`Scraping completado: ${msg.total} productos`, "ok");
      state.products = msg.products;
      renderTable(state.products);
      updateStats();
    }

    if (msg.type === "error") {
      evts.close();
      $("scrape-btn").disabled = false;
      $("scrape-progress-label").textContent = "Error";
      log("Error en scraping: " + msg.msg, "err");
    }
  };

  evts.onerror = () => {
    evts.close();
    $("scrape-btn").disabled = false;
    // Si el stream cerró porque terminó, está bien
  };
});

/* ── Cargar productos locales al iniciar ─────────────────────────────────── */
async function loadLocalProducts() {
  try {
    const products = await fetch("/api/products/local").then(r => r.json());
    if (products.length) {
      state.products = products;
      $("scrape-badge").textContent = `${products.length} productos (cache)`;
      $("scrape-badge").className = "badge badge-blue";
      renderTable(products);
      updateStats();
      log(`${products.length} productos cargados desde cache local`, "info");
    }
  } catch(e) {}
}

/* ── Tabla ────────────────────────────────────────────────────────────────── */
function tokenMatch(text, tokens) {
  const t = text.toLowerCase();
  return tokens.every(tok => t.includes(tok));
}

function scoreProduct(p, tokens) {
  const name = p.name.toLowerCase();
  // Puntuación: +10 si el nombre empieza por el primer token, +1 por cada token encontrado consecutivo
  let score = 0;
  if (tokens.length && name.startsWith(tokens[0])) score += 10;
  // Coincidencia exacta completa
  if (name.includes(tokens.join(' '))) score += 20;
  tokens.forEach(tok => { if (name.includes(tok)) score += 1; });
  return score;
}

function renderTable(products) {
  const rawSearch = $('search-input').value.trim();
  const tokens    = rawSearch.toLowerCase().split(/\s+/).filter(Boolean);
  const filter    = $('filter-status').value;

  let rows = products.filter(p => {
    const isNew = !state.shopifyHandles.has(p.slug);
    if (filter === 'new'      && !isNew)     return false;
    if (filter === 'existing' && isNew)      return false;
    if (filter === 'sale'     && !p.discount) return false;
    const ean = p.ean || state.shopifyBarcodes[p.slug] || "";
    if (tokens.length && !tokenMatch(p.name, tokens) &&
                         !tokenMatch(p.brand, tokens) &&
                         !tokenMatch(ean, tokens)) return false;
    return true;
  });

  // Ordenar por relevancia cuando hay búsqueda
  if (tokens.length) {
    rows = rows.sort((a, b) => scoreProduct(b, tokens) - scoreProduct(a, tokens));
  }

  state.filteredSlugs = rows.map(p => p.slug);

  const tbody = $("products-tbody");
  tbody.innerHTML = "";

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-state"><div>
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#555" stroke-width="1.5">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg><p>Sin resultados</p></div></td></tr>`;
    updateUploadButtons();
    return;
  }

  rows.forEach(p => {
    const isNew    = !state.shopifyHandles.has(p.slug);
    const checked  = state.selected.has(p.slug) ? "checked" : "";
    const img      = p.image || p.images?.[0] || "";
    const imgEl    = img
      ? `<img src="${escHtml(img)}" alt="${escHtml(p.name)}" loading="lazy" data-slug="${p.slug}" class="product-thumb-click" title="Ver fotos" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2244%22 height=%2244%22><rect width=%2244%22 height=%2244%22 fill=%22%231e2535%22/></svg>'">`
      : `<div style="width:44px;height:44px;background:var(--bg3);border-radius:6px;cursor:pointer" class="product-thumb-click" data-slug="${p.slug}" title="Ver fotos"></div>`;

    const ean      = p.ean || state.shopifyBarcodes[p.slug] || "";
    const priceTxt = p.price ? `${p.price.toFixed(2)} €` : "—";
    const discTxt  = p.discount ? `<span class="tag-discount">-${p.discount}%</span>` : "—";
    const statusEl = p.source === 'shopify'
      ? `<span class="tag-existing">En Shopify</span>`
      : isNew
        ? `<span class="tag-new">Nuevo</span>`
        : `<span class="tag-existing">En Shopify</span>`;
    const eanEl  = ean ? `<span style="font-size:11px;color:var(--muted);font-family:monospace">${escHtml(ean)}</span>` : `<span style="color:#444">—</span>`;
    const stockEl = p.inStock
      ? `<span style="color:var(--green);font-size:11px">✓ ${p.stock > 1 ? p.stock + ' uds' : 'Stock'}</span>`
      : `<span class="tag-nostock">Sin stock</span>`;
    const productUrl = p.productUrl ? `href="${escHtml(p.productUrl)}" target="_blank" rel="noopener"` : "";

    const tr = document.createElement("tr");
    tr.dataset.slug = p.slug;
    tr.className    = state.selected.has(p.slug) ? "selected" : "";
    tr.innerHTML = `
      <td><input type="checkbox" class="row-check" data-slug="${p.slug}" ${checked}/></td>
      <td class="td-img">${imgEl}</td>
      <td class="td-name"><a ${productUrl}>${escHtml(p.name)}</a></td>
      <td>${escHtml(p.brand || "—")}</td>
      <td>${escHtml(p.category || "—")}</td>
      <td>${eanEl}</td>
      <td style="white-space:nowrap">${priceTxt}</td>
      <td>${discTxt}</td>
      <td>${statusEl}</td>
      <td>${stockEl}</td>
    `;
    tbody.appendChild(tr);
  });

  // Click en miniatura → abrir modal de producto
  tbody.querySelectorAll(".product-thumb-click").forEach(el => {
    el.addEventListener("click", () => {
      const slug = el.dataset.slug;
      const prod = state.products.find(p => p.slug === slug);
      if (prod) openProductModal(prod);
    });
  });

  // Checkbox events
  tbody.querySelectorAll(".row-check").forEach(cb => {
    cb.addEventListener("change", () => {
      const slug = cb.dataset.slug;
      if (cb.checked) state.selected.add(slug);
      else            state.selected.delete(slug);
      const row = cb.closest("tr");
      row.className = cb.checked ? "selected" : "";
      updateUploadButtons();
    });
  });

  updateUploadButtons();
}

function updateStats() {
  const total  = state.products.length;
  const newP   = state.products.filter(p => !state.shopifyHandles.has(p.slug)).length;
  const sale   = state.products.filter(p => p.discount).length;
  $("stat-total").textContent = total;
  $("stat-new").textContent   = newP;
  $("stat-exist").textContent = total - newP;
  $("stat-sale").textContent  = sale;
}

function updateUploadButtons() {
  const hasProducts = state.products.length > 0;
  const newCount    = state.products.filter(p => !state.shopifyHandles.has(p.slug)).length;

  $("upload-selected-btn").disabled = state.selected.size === 0;
  $("upload-all-btn").disabled      = newCount === 0;
  $("sel-count").textContent        = state.selected.size;
  updateSyncButtons();
}

// Filtros en tiempo real
$("search-input").addEventListener("input",  () => renderTable(state.products));
$("filter-status").addEventListener("change", () => renderTable(state.products));

// Selección masiva
$("select-all-btn").addEventListener("click", () => {
  const newSlugs = state.products
    .filter(p => !state.shopifyHandles.has(p.slug))
    .map(p => p.slug);
  newSlugs.forEach(s => state.selected.add(s));
  renderTable(state.products);
});

$("deselect-all-btn").addEventListener("click", () => {
  state.selected.clear();
  renderTable(state.products);
});

$("check-all").addEventListener("change", function() {
  state.filteredSlugs.forEach(s => {
    if (this.checked) state.selected.add(s);
    else              state.selected.delete(s);
  });
  renderTable(state.products);
});

/* ── Upload ───────────────────────────────────────────────────────────────── */
function startUpload(slugs) {
  const collection      = $("collection-input").value.trim();
  const updateExisting  = $("update-existing").checked;

  $("upload-selected-btn").disabled = true;
  $("upload-all-btn").disabled      = true;
  $("upload-progress").classList.remove("hidden");
  $("upload-bar").style.width = "0%";
  $("upload-progress-label").textContent = "Iniciando…";
  setMsg("upload-msg", "", "");

  const label = slugs.length ? `${slugs.length} seleccionados` : "todos los nuevos";
  log(`Iniciando upload: ${label}`, "info");

  fetch("/api/upload", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slugs, collection, updateExisting }),
  }).then(r => r.json()).then(data => {
    if (data.error) { log("Error: " + data.error, "err"); return; }

    const evts = new EventSource("/api/upload/stream");

    evts.onmessage = ev => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "ping") return;
      if (msg.type === "log")  { log(msg.msg); return; }

      if (msg.type === "progress") {
        const pct = Math.round((msg.current / msg.total) * 100);
        $("upload-bar").style.width = pct + "%";
        $("upload-progress-label").textContent =
          `${msg.current}/${msg.total} · ${escHtml(msg.name)}`;
      }

      if (msg.type === "done") {
        evts.close();
        $("upload-bar").style.width = "100%";
        $("upload-progress-label").textContent = "✓ Completado";
        log(`Upload completado: +${msg.created} creados, ${msg.updated} actualizados`, "ok");
        showResultModal(msg);
        updateUploadButtons();
        loadShopifyHandles(); // refrescar badges
      }

      if (msg.type === "error") {
        evts.close();
        log("Error en upload: " + msg.msg, "err");
        setMsg("upload-msg", msg.msg, "err");
        updateUploadButtons();
      }
    };

    evts.onerror = () => { evts.close(); updateUploadButtons(); };
  }).catch(e => {
    log("Error: " + e.message, "err");
    updateUploadButtons();
  });
}

$("upload-selected-btn").addEventListener("click", () => {
  startUpload([...state.selected]);
});

$("upload-all-btn").addEventListener("click", () => {
  const newSlugs = state.products
    .filter(p => !state.shopifyHandles.has(p.slug))
    .map(p => p.slug);
  startUpload(newSlugs);
});

/* ── Modal ────────────────────────────────────────────────────────────────── */
function showResultModal(data) {
  $("modal-content").innerHTML = `
    <div class="result-grid">
      <div class="result-item">
        <div class="num" style="color:var(--green)">${data.created}</div>
        <div class="lbl">Creados</div>
      </div>
      <div class="result-item">
        <div class="num" style="color:var(--accent)">${data.updated}</div>
        <div class="lbl">Actualizados</div>
      </div>
      <div class="result-item">
        <div class="num" style="color:var(--text-muted)">${data.skipped}</div>
        <div class="lbl">Omitidos</div>
      </div>
      <div class="result-item">
        <div class="num" style="color:var(--red)">${data.errors}</div>
        <div class="lbl">Errores</div>
      </div>
    </div>`;
  $("result-modal").classList.remove("hidden");
}

$("modal-close").addEventListener("click", () => {
  $("result-modal").classList.add("hidden");
});

/* ── Log controls ─────────────────────────────────────────────────────────── */
$("clear-log-btn").addEventListener("click", () => {
  $("log-box").innerHTML = "";
});

/* ── Modal Producto ───────────────────────────────────────────────────────── */
const pmState = { images: [], current: 0 };

function openProductModal(p) {
  const imgs = [
    ...(p.localImages || []),
    ...(p.images     || []),
    ...(p.image ? [p.image] : []),
  ].filter((v, i, a) => v && a.indexOf(v) === i); // únicos no vacíos

  pmState.images  = imgs.length ? imgs : [""];
  pmState.current = 0;

  $('pm-title').textContent = p.name || "";

  const isNew = !state.shopifyHandles.has(p.slug);
  $('pm-badges').innerHTML = [
    isNew ? `<span class="tag-new">Nuevo</span>` : `<span class="tag-existing">En Shopify</span>`,
    p.discount ? `<span class="tag-discount">-${p.discount}%</span>` : "",
    !p.inStock ? `<span class="tag-nostock">Sin stock</span>` : "",
  ].join("");

  $('pm-meta').innerHTML = [
    p.brand    ? `<span><strong>Marca</strong> ${escHtml(p.brand)}</span>` : "",
    p.category ? `<span><strong>Categoría</strong> ${escHtml(p.category)}</span>` : "",
    imgs.length ? `<span><strong>Fotos</strong> ${imgs.length}</span>` : "",
    p.slug     ? `<span><strong>Handle</strong> ${escHtml(p.slug)}</span>` : "",
  ].join("");

  let priceHtml = "";
  if (p.price)         priceHtml += `<span class="pm-price">${p.price.toFixed(2)} €</span>`;
  if (p.originalPrice) priceHtml += `<span class="pm-orig-price">${p.originalPrice.toFixed(2)} €</span>`;
  $('pm-price-row').innerHTML = priceHtml;

  $('pm-desc').textContent = p.description || "";

  const link = $('pm-link');
  if (p.productUrl) { link.href = p.productUrl; link.style.display = ""; }
  else              { link.style.display = "none"; }

  pmRender();
  $('product-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function pmRender() {
  const imgs = pmState.images;
  const cur  = pmState.current;
  const src  = imgs[cur] || "";

  const mainImg = $('pm-main-img');
  mainImg.classList.remove('zoomed');
  mainImg.style.opacity = '0';
  mainImg.src = src;
  mainImg.onload  = () => { mainImg.style.opacity = '1'; };
  mainImg.onerror = () => {
    mainImg.src = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><rect width='400' height='400' fill='%231e2535'/><text x='50%25' y='50%25' fill='%23445' text-anchor='middle' dominant-baseline='middle' font-size='14'>Sin imagen</text></svg>";
    mainImg.style.opacity = '1';
  };

  $('pm-img-counter').textContent = imgs.length > 1 ? `${cur + 1} / ${imgs.length}` : "";
  $('pm-prev').disabled = cur === 0;
  $('pm-next').disabled = cur === imgs.length - 1;

  const thumbsEl = $('pm-thumbs');
  thumbsEl.innerHTML = "";
  imgs.forEach((s, i) => {
    const img = document.createElement('img');
    img.className = 'pm-thumb' + (i === cur ? ' active' : '');
    img.src = s; img.alt = `Foto ${i + 1}`; img.loading = 'lazy';
    img.addEventListener('click', () => { pmState.current = i; pmRender(); });
    thumbsEl.appendChild(img);
  });
  const activeThumb = thumbsEl.querySelector('.active');
  if (activeThumb) activeThumb.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

function closeProductModal() {
  $('product-modal').classList.add('hidden');
  document.body.style.overflow = '';
}

$('pm-prev').addEventListener('click', () => {
  if (pmState.current > 0) { pmState.current--; pmRender(); }
});
$('pm-next').addEventListener('click', () => {
  if (pmState.current < pmState.images.length - 1) { pmState.current++; pmRender(); }
});

$('pm-main-img').addEventListener('click', function() {
  this.classList.toggle('zoomed');
});

$('product-modal-close').addEventListener('click', closeProductModal);
$('product-modal').addEventListener('click', e => {
  if (e.target === $('product-modal')) closeProductModal();
});

document.addEventListener('keydown', e => {
  if ($('product-modal').classList.contains('hidden')) return;
  if (e.key === 'Escape')      closeProductModal();
  if (e.key === 'ArrowLeft'  && pmState.current > 0)                         { pmState.current--; pmRender(); }
  if (e.key === 'ArrowRight' && pmState.current < pmState.images.length - 1) { pmState.current++; pmRender(); }
});

/* ── Sync precio + stock ──────────────────────────────────────────────────── */
function updateSyncButtons() {
  const hasProducts = state.products.length > 0;
  const existCount  = state.products.filter(p => state.shopifyHandles.has(p.slug)).length;
  const selExist    = [...state.selected].filter(s => state.shopifyHandles.has(s)).length;

  $("sync-selected-btn").disabled = selExist === 0;
  $("sync-all-btn").disabled      = existCount === 0;
  $("sync-sel-count").textContent = selExist;
}

function startSync(slugs) {
  const dryRun = $("sync-dry-run").checked;

  $("sync-selected-btn").disabled = true;
  $("sync-all-btn").disabled      = true;
  $("sync-progress").classList.remove("hidden");
  $("sync-bar").style.width = "0%";
  $("sync-progress-label").textContent = "Iniciando…";
  setMsg("sync-msg", "", "");

  const label = slugs.length ? `${slugs.length} seleccionados` : "todos los existentes";
  log(`Iniciando sync precio/stock: ${label}${dryRun ? " (DRY-RUN)" : ""}`, "info");

  fetch("/api/sync", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slugs, dryRun }),
  }).then(r => r.json()).then(data => {
    if (data.error) { log("Error: " + data.error, "err"); updateSyncButtons(); return; }

    const evts = new EventSource("/api/sync/stream");

    evts.onmessage = ev => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "ping") return;
      if (msg.type === "log")  { log(msg.msg); return; }

      if (msg.type === "progress") {
        const pct = Math.round((msg.current / msg.total) * 100);
        $("sync-bar").style.width = pct + "%";
        $("sync-progress-label").textContent =
          `${msg.current}/${msg.total} · ${escHtml(msg.name)}`;
      }

      if (msg.type === "done") {
        evts.close();
        $("sync-bar").style.width = "100%";
        $("sync-progress-label").textContent = "✓ Completado";
        log(`Sync completado: ${msg.updated} actualizados, ` +
            `${msg.not_found} no encontrados, ${msg.errors} errores`, "ok");
        setMsg("sync-msg",
               `✓ ${msg.updated} actualizados · ${msg.not_found} no en Shopify · ${msg.errors} errores`,
               msg.errors ? "err" : "ok");
        updateSyncButtons();
      }

      if (msg.type === "error") {
        evts.close();
        log("Error en sync: " + msg.msg, "err");
        setMsg("sync-msg", msg.msg, "err");
        updateSyncButtons();
      }
    };

    evts.onerror = () => { evts.close(); updateSyncButtons(); };
  }).catch(e => {
    log("Error: " + e.message, "err");
    updateSyncButtons();
  });
}

$("sync-selected-btn").addEventListener("click", () => {
  const selExist = [...state.selected].filter(s => state.shopifyHandles.has(s));
  startSync(selExist);
});

$("sync-all-btn").addEventListener("click", () => {
  const existSlugs = state.products
    .filter(p => state.shopifyHandles.has(p.slug))
    .map(p => p.slug);
  startSync(existSlugs);
});

/* ── Shopify por tag + scrape imágenes PadelPoint ────────────────────────── */
const shopifyTagProducts = [];  // productos Shopify cargados por tag
const shopifyTagSelected = new Set();

// Cargar tags disponibles
async function loadTags() {
  const btn = $('load-tags-btn');
  btn.textContent = '…';
  btn.disabled = true;
  try {
    const data = await fetch('/api/shopify/tags').then(r => r.json());
    if (data.error) { log('Tags: ' + data.error, 'err'); return; }
    const sel = $('tag-select');
    sel.innerHTML = '<option value="">— selecciona un tag —</option>';
    data.tags.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t; opt.textContent = t;
      // Preseleccionar "padel scraper" si existe
      if (t.toLowerCase() === 'padel scraper') opt.selected = true;
      sel.appendChild(opt);
    });
    $('load-by-tag-btn').disabled = !sel.value;
    log(`${data.tags.length} tags cargados`, 'ok');
  } catch(e) { log('Error cargando tags: ' + e.message, 'err'); }
  finally { btn.textContent = '↺'; btn.disabled = false; }
}

$('load-tags-btn').addEventListener('click', loadTags);
$('tag-select').addEventListener('change', () => {
  $('load-by-tag-btn').disabled = !$('tag-select').value;
});

$('load-by-tag-btn').addEventListener('click', async () => {
  const tag = $('tag-select').value;
  if (!tag) return;
  const btn = $('load-by-tag-btn');
  btn.disabled = true; btn.textContent = 'Cargando…';
  try {
    const data = await fetch(`/api/shopify/products-by-tag?tag=${encodeURIComponent(tag)}`).then(r => r.json());
    if (data.error) { log('Error: ' + data.error, 'err'); return; }
    shopifyTagProducts.length = 0;
    shopifyTagProducts.push(...data.products);
    shopifyTagSelected.clear();
    renderShopifyTable(shopifyTagProducts);
    $('shopify-products-info').textContent = `${data.total} productos con tag "${tag}"`;
    $('scrape-images-all-btn').disabled = data.total === 0;
    log(`${data.total} productos Shopify cargados con tag "${tag}"`, 'ok');
  } catch(e) { log('Error: ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = 'Cargar productos con este tag'; }
});

function renderShopifyTable(products) {
  // Reutilizar la tabla principal pero con modo "shopify"
  const tbody = $('products-tbody');
  tbody.innerHTML = '';
  if (!products.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-state"><div><p>Sin productos con este tag</p></div></td></tr>`;
    updateImgScrButtons();
    return;
  }
  products.forEach(p => {
    const checked = shopifyTagSelected.has(p.id) ? 'checked' : '';
    const img = p.image_url || '';
    const imgEl = img
      ? `<img src="${escHtml(img)}" alt="${escHtml(p.title)}" loading="lazy" style="width:44px;height:44px;object-fit:cover;border-radius:6px">`
      : `<div style="width:44px;height:44px;background:var(--bg3);border-radius:6px"></div>`;
    const tr = document.createElement('tr');
    tr.dataset.id = p.id;
    tr.className  = shopifyTagSelected.has(p.id) ? 'selected' : '';
    tr.innerHTML = `
      <td><input type="checkbox" class="shopify-row-check" data-id="${p.id}" ${checked}/></td>
      <td class="td-img">${imgEl}</td>
      <td class="td-name"><a href="https://${state.shopifyStore || ''}/products/${p.handle}" target="_blank">${escHtml(p.title)}</a></td>
      <td>${escHtml(p.vendor || '—')}</td>
      <td>${escHtml(p.product_type || '—')}</td>
      <td>${p.price ? parseFloat(p.price).toFixed(2) + ' €' : '—'}</td>
      <td>—</td>
      <td><span class="tag-existing">En Shopify</span></td>
      <td>—</td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('.shopify-row-check').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) shopifyTagSelected.add(cb.dataset.id);
      else            shopifyTagSelected.delete(cb.dataset.id);
      cb.closest('tr').className = cb.checked ? 'selected' : '';
      updateImgScrButtons();
    });
  });
  updateImgScrButtons();
}

function updateImgScrButtons() {
  $('scrape-images-selected-btn').disabled = shopifyTagSelected.size === 0;
  $('img-sel-count').textContent = shopifyTagSelected.size;
  $('scrape-images-all-btn').disabled = shopifyTagProducts.length === 0;
}

function startImageScrape(products) {
  if (!products.length) return;
  $('scrape-images-selected-btn').disabled = true;
  $('scrape-images-all-btn').disabled = true;
  $('imgscr-progress').classList.remove('hidden');
  $('imgscr-bar').style.width = '0%';
  $('imgscr-progress-label').textContent = 'Iniciando…';
  setMsg('imgscr-msg', '', '');
  log(`Scrapeando imágenes para ${products.length} productos…`, 'info');

  fetch('/api/scrape/images-from-shopify', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ products }),
  }).then(() => {
    const evts = new EventSource('/api/scrape/images-from-shopify/stream');
    evts.onmessage = ev => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'ping') return;
      if (msg.type === 'log') { log(msg.msg); return; }
      if (msg.type === 'progress') {
        const pct = Math.round((msg.current / msg.total) * 100);
        $('imgscr-bar').style.width = pct + '%';
        $('imgscr-progress-label').textContent = `${msg.current}/${msg.total} · ${msg.name}`;
      }
      if (msg.type === 'done') {
        evts.close();
        $('imgscr-bar').style.width = '100%';
        $('imgscr-progress-label').textContent = `✓ ${msg.updated} actualizados`;
        setMsg('imgscr-msg', `✓ ${msg.updated} imágenes actualizadas · ${msg.skipped} sin resultados · ${msg.errors} errores`, 'ok');
        log(`Scrape imágenes completado: ${msg.updated} actualizados, ${msg.skipped} sin resultados, ${msg.errors} errores`, 'ok');
        updateImgScrButtons();
      }
      if (msg.type === 'error') {
        evts.close();
        log('Error: ' + msg.msg, 'err');
        setMsg('imgscr-msg', msg.msg, 'err');
        updateImgScrButtons();
      }
    };
    evts.onerror = () => { evts.close(); updateImgScrButtons(); };
  }).catch(e => { log('Error: ' + e.message, 'err'); updateImgScrButtons(); });
}

$('scrape-images-selected-btn').addEventListener('click', () => {
  const selected = shopifyTagProducts.filter(p => shopifyTagSelected.has(p.id));
  startImageScrape(selected);
});

$('scrape-images-all-btn').addEventListener('click', () => {
  startImageScrape(shopifyTagProducts);
});

/* ── Init ─────────────────────────────────────────────────────────────────── */
(async function init() {
  await loadConfig();
  await loadLocalProducts();
  // Cargar tags automáticamente si ya hay credenciales configuradas
  if (state.shopifyConfigured) loadTags();
})();

