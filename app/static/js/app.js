const state = {
  editorKey: sessionStorage.getItem("editorKey") || "",
  editor: null,
  shops: [],
  chains: [],
  drinks: [],
  compare: [],
  dashboard: [],
  audit: [],
  activeView: "dashboard",
  editingShopId: null,
};

localStorage.removeItem("editorKey");

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(amount, currency = "SGD") {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function fixedAmount(amount) {
  const value = Number(amount);
  return Number.isFinite(value) ? value.toFixed(2) : "";
}

function displaySize(price) {
  return price?.size_category || "Not sure";
}

function showMessage(text, isError = false) {
  const message = $("#message");
  message.textContent = text || "";
  message.classList.toggle("error", isError);
  if (text) {
    window.clearTimeout(showMessage.timer);
    showMessage.timer = window.setTimeout(() => {
      message.textContent = "";
      message.classList.remove("error");
    }, 4000);
  }
}

function setInlineStatus(selector, text) {
  const status = $(selector);
  if (!status) return;
  status.textContent = text || "";
  status.classList.toggle("hidden", !text);
}

function normalizeKey(value) {
  return String(value || "").toLocaleLowerCase().trim().replace(/\s+/g, " ");
}

function findLocalShopDuplicate(data, excludeShopId = null) {
  const wantedName = normalizeKey(data.name);
  const wantedLocation = normalizeKey(data.location);
  const wantedAddress = normalizeKey(data.address);
  const wantedChain = normalizeKey(data.chain_name);

  return state.shops.find((shop) => {
    if (excludeShopId && shop.id === Number(excludeShopId)) {
      return false;
    }
    const sameNameLocation =
      normalizeKey(shop.name) === wantedName && normalizeKey(shop.location) === wantedLocation;
    const sameAddress = wantedAddress && normalizeKey(shop.address) === wantedAddress;
    const sameChainLocation =
      wantedChain &&
      shop.chain &&
      normalizeKey(shop.chain.name) === wantedChain &&
      normalizeKey(shop.location) === wantedLocation;
    return sameNameLocation || sameAddress || sameChainLocation;
  });
}

function setFormBusy(form, busy, busyText = "Saving...") {
  form.dataset.busy = busy ? "true" : "false";
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  if (!button.dataset.defaultText) {
    button.dataset.defaultText = button.textContent;
  }
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.defaultText;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (state.editorKey) {
    headers.set("X-Editor-Key", state.editorKey);
  }

  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function queryParams() {
  const params = new URLSearchParams();
  const search = $("#search").value.trim();
  const minPrice = $("#min-price").value;
  const maxPrice = $("#max-price").value;
  const sortBy = $("#sort-by").value;
  if (search) params.set("search", search);
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  if (sortBy) params.set("sort_by", sortBy);
  return params.toString();
}

async function loadAll() {
  await Promise.all([
    loadDrinks(),
    loadChains(),
    loadDashboard(),
    loadDirectory(),
    loadCompare(),
    state.editor ? loadAudit() : Promise.resolve((state.audit = [])),
  ]);
  fillSelects();
  render();
}

async function loadDashboard() {
  const qs = queryParams();
  state.dashboard = await api(`/api/dashboard/shop-averages${qs ? `?${qs}` : ""}`);
}

async function loadDirectory() {
  const qs = queryParams();
  state.shops = await api(`/api/shops${qs ? `?${qs}` : ""}`);
}

async function loadCompare() {
  const qs = queryParams();
  state.compare = await api(`/api/compare${qs ? `?${qs}` : ""}`);
}

async function loadChains() {
  state.chains = await api("/api/chains");
}

async function loadDrinks() {
  state.drinks = await api("/api/drinks");
}

async function loadAudit() {
  state.audit = await api("/api/audit?limit=80");
}

async function authenticate() {
  $("#editor-key").value = state.editorKey;
  if (!state.editorKey) {
    state.editor = null;
    updateEditorStatus();
    return;
  }
  try {
    state.editor = await api("/api/users/me");
  } catch {
    state.editor = null;
    sessionStorage.removeItem("editorKey");
    localStorage.removeItem("editorKey");
    state.editorKey = "";
  }
  updateEditorStatus();
}

function updateEditorStatus() {
  $("#editor-status").textContent = state.editor ? state.editor.name : "Viewing";
  $("#editor-name").textContent = state.editor ? state.editor.name : "Editor key required";
  document.body.classList.toggle("is-editor", Boolean(state.editor));
}

function fillSelect(select, rows, getLabel) {
  if (!select) return;
  const current = select.value;
  select.innerHTML = rows
    .map((row) => `<option value="${escapeHtml(row.id)}">${escapeHtml(getLabel(row))}</option>`)
    .join("");
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function drinkLabel(drink) {
  return `${drink.name} (${drink.drink_type})`;
}

function findDrinkBySearchValue(value) {
  const normalized = normalizeKey(value);
  if (!normalized) return null;
  const labelMatch = state.drinks.find((drink) => normalizeKey(drinkLabel(drink)) === normalized);
  if (labelMatch) return labelMatch;

  const nameMatches = state.drinks.filter((drink) => normalizeKey(drink.name) === normalized);
  return nameMatches.length === 1 ? nameMatches[0] : null;
}

function setPriceDrink(drinkId) {
  const drink = findDrink(drinkId);
  const hidden = $("#price-drink");
  const search = $("#price-drink-search");
  if (!hidden || !search) return;
  hidden.value = drink ? String(drink.id) : "";
  search.value = drink ? drinkLabel(drink) : "";
}

function syncPriceDrinkSelection() {
  const hidden = $("#price-drink");
  const search = $("#price-drink-search");
  if (!hidden || !search) return null;
  const drink = findDrinkBySearchValue(search.value);
  hidden.value = drink ? String(drink.id) : "";
  return drink;
}

function openDrinkFormFromPriceSearch() {
  const search = $("#price-drink-search");
  const typed = search?.value.trim() || "";
  setActiveView("editor");
  const drinksTool = $("#drinks-tool");
  if (drinksTool) {
    drinksTool.open = true;
    drinksTool.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  const drinkForm = $("#drink-form");
  if (drinkForm && typed) {
    drinkForm.elements.name.value = typed.replace(/\s+\([^)]*\)\s*$/, "");
    drinkForm.elements.drink_type.focus();
  }
  setInlineStatus(
    "#drink-save-status",
    typed ? `Add "${typed}" here, then the Prices section will select it for you.` : ""
  );
}

function fillSelects() {
  const shopRows = state.shops.map((shop) => ({
    id: shop.id,
    label: `${shop.name} - ${shop.location}`,
  }));
  ["#price-shop", "#copy-source", "#copy-target"].forEach((selector) => {
    fillSelect($(selector), shopRows, (shop) => shop.label);
  });
  fillSelect($("#template-drink"), state.drinks, drinkLabel);
  fillSelect($("#copy-drinks"), state.drinks, drinkLabel);
  const currentPriceDrinkId = $("#price-drink")?.value;
  const priceDrinkOptions = $("#price-drink-options");
  if (priceDrinkOptions) {
    priceDrinkOptions.innerHTML = state.drinks
      .map((drink) => `<option value="${escapeHtml(drinkLabel(drink))}"></option>`)
      .join("");
  }
  if (currentPriceDrinkId) {
    setPriceDrink(currentPriceDrinkId);
  }
  ["#template-chain", "#sync-chain"].forEach((selector) => {
    fillSelect($(selector), state.chains, (chain) => chain.name);
  });
  const chainOptions = $("#chain-options");
  if (chainOptions) {
    chainOptions.innerHTML = state.chains
      .map((chain) => `<option value="${escapeHtml(chain.name)}"></option>`)
      .join("");
  }
  const drinkTypes = [...new Set(state.drinks.map((drink) => drink.drink_type))]
    .sort((left, right) => left.localeCompare(right));
  const drinkTypeOptions = $("#drink-type-options");
  if (drinkTypeOptions) {
    drinkTypeOptions.innerHTML = drinkTypes
      .map((type) => `<option value="${escapeHtml(type)}"></option>`)
      .join("");
  }
}

function render() {
  renderDashboard();
  renderDirectory();
  renderCompare();
  renderChains();
  renderManageShops();
  renderDrinks();
  renderAudit();
  updateEditorStatus();
}

function renderDashboard() {
  const count = $("#dashboard-count");
  const summary = $("#dashboard-summary");
  const list = $("#shop-average-list");
  if (!count || !summary || !list) return;

  count.textContent = `${state.dashboard.length} shops with prices`;
  if (!state.dashboard.length) {
    summary.innerHTML = "";
    list.innerHTML = `<div class="empty">No priced drinks match the current filters.</div>`;
    return;
  }

  const prices = state.dashboard.map((row) => row.average_price);
  const totalPrices = state.dashboard.reduce((total, row) => total + row.price_count, 0);
  const overallAverage = prices.reduce((total, price) => total + price, 0) / prices.length;
  const lowest = state.dashboard.reduce((best, row) =>
    row.average_price < best.average_price ? row : best
  );
  const highest = state.dashboard.reduce((best, row) =>
    row.average_price > best.average_price ? row : best
  );
  const maxAverage = Math.max(...prices);

  summary.innerHTML = `
    <article class="metric-card">
      <span>Overall average</span>
      <strong>${money(overallAverage)}</strong>
      <p class="meta">${totalPrices} priced drinks tracked</p>
    </article>
    <article class="metric-card">
      <span>Lowest shop average</span>
      <strong>${money(lowest.average_price, lowest.currency)}</strong>
      <p class="meta">${escapeHtml(lowest.shop_name)}</p>
    </article>
    <article class="metric-card">
      <span>Highest shop average</span>
      <strong>${money(highest.average_price, highest.currency)}</strong>
      <p class="meta">${escapeHtml(highest.shop_name)}</p>
    </article>
  `;

  list.innerHTML = state.dashboard
    .map((row, index) => {
      const chain = row.chain || "Independent";
      const width = maxAverage ? Math.max((row.average_price / maxAverage) * 100, 8) : 8;
      return `<article class="average-row">
        <div class="average-rank">${index + 1}</div>
        <div class="average-main">
          <div class="average-head">
            <div>
              <h3>${escapeHtml(row.shop_name)}</h3>
              <p class="meta">${escapeHtml(chain)} | ${escapeHtml(row.location)}</p>
            </div>
            <strong>${money(row.average_price, row.currency)}</strong>
          </div>
          <div class="average-bar" aria-hidden="true"><span style="width: ${width}%"></span></div>
          <p class="meta">
            ${row.price_count} prices | Cheapest: ${escapeHtml(row.min_drink)} ${money(row.min_price, row.currency)}
            | Priciest: ${escapeHtml(row.max_drink)} ${money(row.max_price, row.currency)}
          </p>
        </div>
      </article>`;
    })
    .join("");
}

function renderDirectory() {
  $("#shop-count").textContent = `${state.shops.length} shops`;
  const list = $("#shop-list");
  if (!state.shops.length) {
    list.innerHTML = `<div class="empty">No shops match the current filters.</div>`;
    return;
  }
  list.innerHTML = state.shops
    .map((shop) => {
      const chain = shop.chain ? `<span class="badge">${escapeHtml(shop.chain.name)}</span>` : "";
      const items = shop.items.length
        ? shop.items.map((item) => menuRow(item)).join("")
        : `<p class="meta">No menu prices yet.</p>`;
      const actions = state.editor
        ? `<div class="actions">
            <button type="button" class="small" data-action="edit-shop" data-shop-id="${shop.id}">Edit</button>
            <button type="button" class="small ghost" data-action="price-shop" data-shop-id="${shop.id}">Prices</button>
            <button type="button" class="small danger" data-action="delete-shop" data-shop-id="${shop.id}">Delete</button>
          </div>`
        : "";
      return `<article class="shop-card">
        <div class="card-head">
          <div>
            <h3>${escapeHtml(shop.name)}</h3>
            <p class="meta">${escapeHtml(shop.location)}${shop.address ? `, ${escapeHtml(shop.address)}` : ""}</p>
          </div>
          <div class="badge-row">${chain}</div>
        </div>
        <div class="menu-list">${items}</div>
        ${actions}
      </article>`;
    })
    .join("");
}

function menuRow(item, template = false) {
  const price = item.price;
  const priceText = price ? money(price.amount, price.currency) : "No price";
  const size = price ? `, ${displaySize(price)}` : "";
  const override = price && price.is_override ? `<span class="badge override">Outlet override</span>` : "";
  const actions = state.editor
    ? `<div class="actions">
        <button type="button" class="small" data-action="${template ? "edit-template-item" : "edit-menu-item"}" data-item-id="${item.id}">Edit</button>
        <button type="button" class="small danger" data-action="${template ? "delete-template-item" : "delete-menu-item"}" data-item-id="${item.id}">Delete</button>
      </div>`
    : "";
  return `<div class="menu-row">
    <div class="menu-name">
      <strong>${escapeHtml(item.drink_name)}</strong>
      <span class="meta">${escapeHtml(item.drink_type)}${escapeHtml(size)}</span>
      <span class="badge-row">${override}</span>
    </div>
    <div>
      <div class="price">${priceText}</div>
      ${actions}
    </div>
  </div>`;
}

function renderCompare() {
  $("#compare-count").textContent = `${state.compare.length} prices`;
  $("#compare-body").innerHTML = state.compare
    .map(
      (row) => `<tr>
        <td>${escapeHtml(row.drink_name)}</td>
        <td>${escapeHtml(row.drink_type)}</td>
        <td>${escapeHtml(row.shop_name)}</td>
        <td>${escapeHtml(row.chain || "Independent")}</td>
        <td>${escapeHtml(row.location)}</td>
        <td><strong>${money(row.price, row.currency)}</strong> <span class="meta">${escapeHtml(row.size_category || "Not sure")}</span></td>
      </tr>`
    )
    .join("");
}

function renderChains() {
  $("#chain-count").textContent = `${state.chains.length} chains`;
  const list = $("#chain-list");
  if (!state.chains.length) {
    list.innerHTML = `<div class="empty">No chains yet.</div>`;
    return;
  }
  list.innerHTML = state.chains
    .map((chain) => {
      const outlets = chain.outlets.length
        ? chain.outlets.map((shop) => `<span class="badge">${escapeHtml(shop.location)}</span>`).join("")
        : `<span class="meta">No outlets</span>`;
      const template = chain.template_items.length
        ? chain.template_items.map((item) => menuRow(item, true)).join("")
        : `<p class="meta">No template items yet.</p>`;
      const sync = state.editor
        ? `<button type="button" class="small" data-action="sync-chain" data-chain-id="${chain.id}">Sync Template</button>`
        : "";
      return `<article class="chain-card">
        <div class="card-head">
          <div>
            <h3>${escapeHtml(chain.name)}</h3>
            <p class="meta">${chain.outlets.length} outlets</p>
          </div>
          ${sync}
        </div>
        <div class="badge-row">${outlets}</div>
        <div class="menu-list">${template}</div>
      </article>`;
    })
    .join("");
}

function renderDrinks() {
  $("#drink-count").textContent = `${state.drinks.length} active`;
  $("#drink-list").innerHTML = state.drinks
    .map(
      (drink) => `<div class="drink-row">
        <div>
          <strong>${escapeHtml(drink.name)}</strong>
          <p class="meta">${escapeHtml(drink.drink_type)}${drink.default_size ? `, ${escapeHtml(drink.default_size)}` : ""}</p>
        </div>
        ${
          state.editor
            ? `<div class="actions">
                <button type="button" class="small" data-action="edit-drink" data-drink-id="${drink.id}">Edit</button>
                <button type="button" class="small danger" data-action="delete-drink" data-drink-id="${drink.id}">Delete</button>
              </div>`
            : ""
        }
      </div>`
    )
    .join("");
}

function renderManageShops() {
  const count = $("#manage-shop-count");
  const list = $("#manage-shop-list");
  if (!count || !list) return;

  count.textContent = `${state.shops.length} active`;
  if (!state.shops.length) {
    list.innerHTML = `<div class="empty">No shops match the current filters.</div>`;
    return;
  }

  list.innerHTML = state.shops
    .map((shop) => {
      const chain = shop.chain ? escapeHtml(shop.chain.name) : "Independent";
      const address = shop.address ? `, ${escapeHtml(shop.address)}` : "";
      const priceCount = shop.items.filter((item) => item.price).length;

      return `<div class="manage-shop">
        <div>
          <strong>${escapeHtml(shop.name)}</strong>
          <p class="meta">${chain} | ${escapeHtml(shop.location)}${address} | ${priceCount} prices</p>
        </div>
        <div class="actions">
          <button type="button" class="small" data-action="edit-shop" data-shop-id="${shop.id}">Edit</button>
          <button type="button" class="small ghost" data-action="price-shop" data-shop-id="${shop.id}">Prices</button>
          <button type="button" class="small danger" data-action="delete-shop" data-shop-id="${shop.id}">Delete</button>
        </div>
      </div>`;
    })
    .join("");
}

function renderAudit() {
  $("#audit-count").textContent = `${state.audit.length} changes`;
  const list = $("#audit-list");
  if (!state.audit.length) {
    list.innerHTML = `<div class="empty">No changes recorded yet.</div>`;
    return;
  }
  list.innerHTML = state.audit
    .map(
      (entry) => `<article class="audit-entry">
        <strong>${escapeHtml(entry.summary)}</strong>
        <p class="meta">${escapeHtml(entry.editor_name)} ${escapeHtml(entry.action)}d ${escapeHtml(entry.entity_type)}</p>
        <time datetime="${escapeHtml(entry.created_at)}">${new Date(entry.created_at).toLocaleString()}</time>
      </article>`
    )
    .join("");
}

function requireEditor() {
  if (!state.editor) {
    showMessage("Set an editor key before making changes.", true);
    return false;
  }
  return true;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function refreshAfterChange(message) {
  await loadAll();
  showMessage(message);
}

function setActiveView(viewId) {
  state.activeView = viewId;
  document
    .querySelectorAll(".tab")
    .forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
  document
    .querySelectorAll(".view")
    .forEach((view) => view.classList.toggle("active", view.id === viewId));
}

function setShopFormMode(shop = null) {
  state.editingShopId = shop ? shop.id : null;
  $("#shop-id").value = shop ? shop.id : "";
  $("#shop-name").value = shop ? shop.name : "";
  $("#shop-location").value = shop ? shop.location : "";
  $("#shop-chain").value = shop?.chain?.name || "";
  $("#shop-address").value = shop?.address || "";
  $("#shop-neighborhood").value = shop?.neighborhood || "";
  $("#shop-form-title").textContent = shop ? "Edit Shop" : "Add Shop";
  $("#shop-form-state").textContent = shop ? shop.name : "New shop";
  $("#shop-submit").textContent = shop ? "Save Shop" : "Add Shop";
  $("#cancel-shop-edit").classList.toggle("hidden", !shop);
}

async function submitShop(event) {
  event.preventDefault();
  if (!requireEditor()) return;
  const form = event.currentTarget;
  if (form.dataset.busy === "true") return;
  const data = formData(form);
  const shopId = data.shop_id;
  delete data.shop_id;
  const duplicate = findLocalShopDuplicate(data, shopId);
  if (duplicate) {
    showMessage(
      `This looks like a duplicate of ${duplicate.name} at ${duplicate.location}.`,
      true
    );
    return;
  }

  setFormBusy(form, true, shopId ? "Saving..." : "Adding...");
  try {
    const saved = await api(shopId ? `/api/shops/${shopId}` : "/api/shops", {
      method: shopId ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    form.reset();
    setShopFormMode(null);
    await refreshAfterChange(
      shopId
        ? `Shop saved: ${saved.name} at ${saved.location}.`
        : `Shop added: ${saved.name} at ${saved.location}.`
    );
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setFormBusy(form, false);
  }
}

async function submitDrink(event) {
  event.preventDefault();
  if (!requireEditor()) return;
  const form = event.currentTarget;
  if (form.dataset.busy === "true") return;
  const data = formData(form);
  data.default_size = data.default_size || null;
  data.description = data.description || null;

  setFormBusy(form, true, "Adding...");
  try {
    const saved = await api("/api/drinks", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadAll();
    const priceTool = $("#prices-tool");
    const priceDrink = $("#price-drink");
    if (priceTool && priceDrink) {
      priceTool.open = true;
      setPriceDrink(saved.id);
    }
    const message = `Drink added: ${saved.name}. Add a shop price for it in the Prices section.`;
    setInlineStatus("#drink-save-status", message);
    showMessage(message);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setFormBusy(form, false);
  }
}

async function submitPrice(event) {
  event.preventDefault();
  if (!requireEditor()) return;
  const form = event.currentTarget;
  if (form.dataset.busy === "true") return;
  const selectedDrink = syncPriceDrinkSelection();
  if (!selectedDrink) {
    openDrinkFormFromPriceSearch();
    showMessage("Choose an existing drink from the search list, or add it first.", true);
    return;
  }
  const data = formData(form);
  const shopId = data.shop_id;
  const shopName = $("#price-shop").selectedOptions[0]?.textContent || "selected shop";
  const drinkName = drinkLabel(selectedDrink);
  delete data.shop_id;
  data.drink_id = Number(data.drink_id);
  data.amount = Number(data.amount);
  data.size_label = data.size_label || null;
  data.notes = data.notes || null;

  setFormBusy(form, true, "Saving...");
  try {
    const saved = await api(`/api/shops/${shopId}/menu/items`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    await loadAll();
    $("#price-shop").value = String(shopId);
    setPriceDrink(saved.drink_id);
    form.elements.amount.value = "";
    form.elements.size_label.value = "";
    form.elements.notes.value = "";
    const priceText = saved.price ? money(saved.price.amount, saved.price.currency) : "the new price";
    const sizeText = saved.price ? ` (${displaySize(saved.price)})` : "";
    const action = saved.created ? "Added new menu item" : "Updated price";
    const message = `${action}: ${drinkName} at ${shopName} is now ${priceText}${sizeText}.`;
    setInlineStatus("#price-save-status", message);
    showMessage(message);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setFormBusy(form, false);
  }
}

async function submitCopy(event) {
  event.preventDefault();
  if (!requireEditor()) return;
  const form = event.currentTarget;
  const selected = [...$("#copy-drinks").selectedOptions].map((option) => Number(option.value));
  const sourceId = form.source_shop_id.value;
  const payload = {
    target_shop_id: Number(form.target_shop_id.value),
    drink_ids: selected.length ? selected : null,
    include_full_menu: form.include_full_menu.checked,
    overwrite_existing: form.overwrite_existing.checked,
  };
  await api(`/api/shops/${sourceId}/copy-menu`, { method: "POST", body: JSON.stringify(payload) });
  await refreshAfterChange("Menu copied.");
}

async function submitTemplate(event) {
  event.preventDefault();
  if (!requireEditor()) return;
  const data = formData(event.currentTarget);
  const chainId = data.chain_id;
  delete data.chain_id;
  data.drink_id = Number(data.drink_id);
  data.amount = Number(data.amount);
  await api(`/api/chains/${chainId}/template/items`, { method: "POST", body: JSON.stringify(data) });
  event.currentTarget.reset();
  await refreshAfterChange("Template item saved.");
}

async function submitSync(event) {
  event.preventDefault();
  if (!requireEditor()) return;
  const form = event.currentTarget;
  const payload = { overwrite_outlet_prices: form.overwrite_outlet_prices.checked };
  await api(`/api/chains/${form.chain_id.value}/sync-template`, { method: "POST", body: JSON.stringify(payload) });
  await refreshAfterChange("Template synced.");
}

function findShop(shopId) {
  return state.shops.find((shop) => shop.id === Number(shopId));
}

function findDrink(drinkId) {
  return state.drinks.find((drink) => drink.id === Number(drinkId));
}

function findMenuItem(menuItemId) {
  const id = Number(menuItemId);
  for (const shop of state.shops) {
    const item = shop.items.find((candidate) => candidate.id === id);
    if (item) {
      return { item, shop, chain: null };
    }
  }
  for (const chain of state.chains) {
    const item = chain.template_items.find((candidate) => candidate.id === id);
    if (item) {
      return { item, shop: null, chain };
    }
  }
  return null;
}

function promptRequired(label, currentValue) {
  const value = prompt(label, currentValue ?? "");
  if (value === null) return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function promptOptional(label, currentValue) {
  const value = prompt(label, currentValue ?? "");
  return value === null ? null : value.trim();
}

async function editShop(shopId) {
  const shop = findShop(shopId);
  if (!shop) return;
  setShopFormMode(shop);
  setActiveView("editor");
  $("#shop-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

function focusPriceForShop(shopId) {
  const shop = findShop(shopId);
  if (!shop) return;
  setActiveView("editor");
  const pricesTool = $("#prices-tool");
  pricesTool.open = true;
  const select = $("#price-shop");
  if ([...select.options].some((option) => option.value === String(shop.id))) {
    select.value = String(shop.id);
  }
  pricesTool.scrollIntoView({ behavior: "smooth", block: "start" });
  showMessage(`Prices selected for ${shop.name}.`);
}

async function deleteShop(shopId) {
  const shop = findShop(shopId);
  if (!shop) return;
  const itemCount = shop.items.length;
  const message = itemCount
    ? `Delete ${shop.name} and hide its ${itemCount} menu items from the directory?`
    : `Delete ${shop.name} from the directory?`;
  if (!confirm(message)) return;

  await api(`/api/shops/${shop.id}`, { method: "DELETE" });
  await refreshAfterChange(`Shop deleted: ${shop.name}.`);
}

async function editMenuItem(menuItemId) {
  const match = findMenuItem(menuItemId);
  if (!match) return;
  const { item, shop, chain } = match;
  const price = item.price;
  const place = shop?.name || `${chain?.name || "Chain"} template`;
  const amountText = promptRequired("Price", price ? fixedAmount(price.amount) : "");
  if (amountText === null) return;
  const amount = Number(amountText);
  if (!Number.isFinite(amount) || amount <= 0) {
    showMessage("Enter a valid price greater than zero.", true);
    return;
  }
  const sizeLabel = promptOptional("Size", price?.size_label || item.default_size || "");
  if (sizeLabel === null) return;
  const notes = promptOptional("Notes", item.notes || "");
  if (notes === null) return;

  await api(`/api/menu-items/${item.id}`, {
    method: "PUT",
    body: JSON.stringify({
      amount,
      size_label: sizeLabel,
      notes,
    }),
  });
  await refreshAfterChange(`Updated ${item.drink_name} at ${place}.`);
}

async function deleteMenuItem(menuItemId) {
  const match = findMenuItem(menuItemId);
  if (!match) return;
  const { item, shop, chain } = match;
  const place = shop?.name || `${chain?.name || "Chain"} template`;
  if (!confirm(`Delete ${item.drink_name} from ${place}?`)) return;

  await api(`/api/menu-items/${item.id}`, { method: "DELETE" });
  await refreshAfterChange(`Deleted ${item.drink_name} from ${place}.`);
}

async function editDrink(drinkId) {
  const drink = findDrink(drinkId);
  if (!drink) return;
  const name = promptRequired("Drink name", drink.name);
  if (name === null) return;
  const drinkType = promptRequired("Drink type", drink.drink_type);
  if (drinkType === null) return;
  const defaultSize = promptOptional("Default size", drink.default_size || "");
  if (defaultSize === null) return;
  const description = promptOptional("Description", drink.description || "");
  if (description === null) return;

  await api(`/api/drinks/${drink.id}`, {
    method: "PUT",
    body: JSON.stringify({
      name,
      drink_type: drinkType,
      default_size: defaultSize,
      description,
    }),
  });
  await refreshAfterChange(`Drink updated: ${name}.`);
}

async function handleActions(event) {
  const button = event.target.closest("[data-action]");
  if (!button || !requireEditor()) return;
  const action = button.dataset.action;
  try {
    if (action === "edit-menu-item" || action === "edit-template-item") {
      await editMenuItem(button.dataset.itemId);
    }
    if (action === "delete-menu-item" || action === "delete-template-item") {
      await deleteMenuItem(button.dataset.itemId);
    }
    if (action === "delete-shop") {
      await deleteShop(button.dataset.shopId);
    }
    if (action === "edit-shop") {
      await editShop(button.dataset.shopId);
    }
    if (action === "price-shop") {
      focusPriceForShop(button.dataset.shopId);
    }
    if (action === "edit-drink") {
      await editDrink(button.dataset.drinkId);
    }
    if (action === "delete-drink") {
      const drink = findDrink(button.dataset.drinkId);
      if (!drink || !confirm(`Delete ${drink.name} from active drink lists?`)) return;
      await api(`/api/drinks/${button.dataset.drinkId}`, { method: "DELETE" });
      await refreshAfterChange(`Drink deleted: ${drink.name}.`);
    }
    if (action === "sync-chain") {
      await api(`/api/chains/${button.dataset.chainId}/sync-template`, {
        method: "POST",
        body: JSON.stringify({ overwrite_outlet_prices: false }),
      });
      await refreshAfterChange("Template synced.");
    }
  } catch (error) {
    showMessage(error.message, true);
  }
}

function bindEvents() {
  $("#editor-login").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.editorKey = $("#editor-key").value.trim();
    sessionStorage.setItem("editorKey", state.editorKey);
    localStorage.removeItem("editorKey");
    await authenticate();
    if (state.editor) {
      await loadAudit();
    } else {
      state.audit = [];
    }
    showMessage(state.editor ? `Editor set: ${state.editor.name}` : "Editor key rejected.", !state.editor);
    render();
  });

  $("#clear-editor").addEventListener("click", () => {
    state.editorKey = "";
    state.editor = null;
    sessionStorage.removeItem("editorKey");
    localStorage.removeItem("editorKey");
    $("#editor-key").value = "";
    updateEditorStatus();
    render();
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      setActiveView(tab.dataset.view);
    });
  });

  ["#search", "#min-price", "#max-price", "#sort-by"].forEach((selector) => {
    $(selector).addEventListener("input", async () => {
      try {
        await Promise.all([loadDashboard(), loadDirectory(), loadCompare()]);
        renderDashboard();
        renderDirectory();
        renderCompare();
      } catch (error) {
        showMessage(error.message, true);
      }
    });
  });

  document.querySelectorAll('input[type="number"][step="0.01"]').forEach((input) => {
    input.addEventListener("blur", () => {
      if (input.value !== "") {
        input.value = fixedAmount(input.value);
      }
    });
  });

  $("#shop-form").addEventListener("submit", submitShop);
  $("#cancel-shop-edit").addEventListener("click", () => {
    $("#shop-form").reset();
    setShopFormMode(null);
  });
  $("#drink-form").addEventListener("submit", submitDrink);
  $("#price-drink-search").addEventListener("input", syncPriceDrinkSelection);
  $("#add-missing-drink").addEventListener("click", openDrinkFormFromPriceSearch);
  $("#price-form").addEventListener("submit", submitPrice);
  $("#copy-form").addEventListener("submit", submitCopy);
  $("#template-form").addEventListener("submit", submitTemplate);
  $("#sync-form").addEventListener("submit", submitSync);
  document.body.addEventListener("click", handleActions);
}

async function init() {
  bindEvents();
  try {
    await authenticate();
    await loadAll();
  } catch (error) {
    showMessage(error.message, true);
  }
}

init();
