/* Products page: list, filters, create/edit modal, actions. */
(function () {
  "use strict";

  var PAGE_SIZE = 10;
  var state = { skip: 0, total: 0, search: "", niche: "", status: "" };
  var loadSeq = 0;

  /**
   * Build the products query string from current state.
   * @returns {string} Query string.
   */
  function queryString() {
    var params = new URLSearchParams();
    params.set("skip", String(state.skip));
    params.set("limit", String(PAGE_SIZE));
    if (state.search) {
      params.set("search", state.search);
    }
    if (state.niche) {
      params.set("niche", state.niche);
    }
    if (state.status) {
      params.set("status", state.status);
    }
    return params.toString();
  }

  /**
   * Format a price as $0.00 (or an em dash when missing/invalid).
   * @param {number|string|null} value - Raw price.
   * @returns {string} Formatted price.
   */
  function formatPrice(value) {
    var n = Number(value);
    return value === null || value === undefined || !isFinite(n)
      ? "\u2014"
      : "$" + n.toFixed(2);
  }

  /**
   * Create a thumbnail image with a graceful fallback box.
   * @param {string|null} url - Image URL.
   * @param {string} title - Alt text.
   * @returns {HTMLElement} Image or placeholder element.
   */
  function thumbnail(url, title) {
    if (!url) {
      var empty = document.createElement("div");
      empty.className = "thumb-fallback";
      empty.textContent = "No image";
      return empty;
    }
    var img = document.createElement("img");
    img.src = url;
    img.alt = title;
    img.className = "w-16 h-16 rounded-lg object-cover flex-shrink-0";
    img.loading = "lazy";
    window.guardImage(img);
    return img;
  }

  /**
   * Build tag chips for a product.
   * @param {Array<string>} tags - Tag list.
   * @returns {HTMLElement} Chips container.
   */
  function tagChips(tags) {
    var wrap = document.createElement("div");
    wrap.className = "flex flex-wrap gap-1";
    (tags || []).slice(0, 5).forEach(function (tag) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = tag;
      wrap.appendChild(chip);
    });
    return wrap;
  }

  /**
   * Build action buttons for a product row or card.
   * @param {Object} product - Product record.
   * @returns {HTMLElement} Actions container.
   */
  function actionButtons(product) {
    var wrap = document.createElement("div");
    wrap.className = "flex flex-wrap gap-1 justify-end";
    var actions = [
      { label: "Edit", name: "edit", cls: "btn-secondary" },
      {
        label: product.status === "active" ? "Archive" : "Activate",
        name: "toggle",
        cls: "btn-secondary"
      },
      { label: "Generate Post", name: "generate", cls: "btn-secondary" }
    ];
    actions.forEach(function (action) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm " + action.cls;
      btn.textContent = action.label;
      btn.dataset.action = action.name;
      btn.dataset.id = String(product.id);
      wrap.appendChild(btn);
    });
    return wrap;
  }

  /**
   * Render products into the desktop table and mobile cards.
   * @param {Array<Object>} items - Product records.
   */
  function renderProducts(items) {
    var tbody = document.getElementById("products-tbody");
    var cards = document.getElementById("products-cards");
    tbody.innerHTML = "";
    cards.innerHTML = "";
    items.forEach(function (product) {
      var row = document.createElement("tr");
      row.className = "border-b border-gray-200 dark:border-slate-700 last:border-0 hover:bg-white/90 dark:hover:bg-slate-800/80 cursor-pointer";
      row.dataset.id = String(product.id);
      var main = document.createElement("td");
      main.className = "px-4 py-3";
      var mainFlex = document.createElement("div");
      mainFlex.className = "flex items-center gap-3";
      mainFlex.appendChild(thumbnail(product.mockup_url, product.title));
      var titleWrap = document.createElement("div");
      titleWrap.className = "min-w-0";
      var title = document.createElement("p");
      title.className = "font-medium truncate max-w-xs text-gray-900 dark:text-slate-100";
      title.textContent = product.title;
      var desc = document.createElement("p");
      desc.className = "text-xs text-gray-500 dark:text-slate-400 truncate max-w-xs";
      desc.textContent = product.description || "";
      titleWrap.appendChild(title);
      titleWrap.appendChild(desc);
      mainFlex.appendChild(titleWrap);
      main.appendChild(mainFlex);
      var nicheCell = document.createElement("td");
      nicheCell.className = "px-4 py-3 text-gray-600 dark:text-slate-300";
      nicheCell.textContent = product.niche;
      var priceCell = document.createElement("td");
      priceCell.className = "px-4 py-3 text-gray-900 dark:text-slate-100";
      priceCell.textContent = formatPrice(product.price);
      var statusCell = document.createElement("td");
      statusCell.className = "px-4 py-3";
      statusCell.innerHTML = window.statusBadge(product.status);
      var tagsCell = document.createElement("td");
      tagsCell.className = "px-4 py-3";
      tagsCell.appendChild(tagChips(product.tags));
      var actionsCell = document.createElement("td");
      actionsCell.className = "px-4 py-3";
      actionsCell.appendChild(actionButtons(product));
      row.appendChild(main);
      row.appendChild(nicheCell);
      row.appendChild(priceCell);
      row.appendChild(statusCell);
      row.appendChild(tagsCell);
      row.appendChild(actionsCell);
      tbody.appendChild(row);

      var card = document.createElement("div");
      card.className = "bg-white/70 dark:bg-slate-900/60 backdrop-blur-md border border-gray-200/60 dark:border-slate-700/50 rounded-xl shadow-lg shadow-gray-200/50 dark:shadow-xl dark:shadow-black/20 p-4 cursor-pointer";
      card.dataset.id = String(product.id);
      var cardTop = document.createElement("div");
      cardTop.className = "flex items-center gap-3 mb-2";
      cardTop.appendChild(thumbnail(product.mockup_url, product.title));
      var cardTitle = document.createElement("div");
      cardTitle.className = "min-w-0 flex-1";
      var cardH = document.createElement("p");
      cardH.className = "font-medium text-gray-900 dark:text-slate-100";
      cardH.textContent = product.title;
      var cardSub = document.createElement("p");
      cardSub.className = "text-xs text-gray-500 dark:text-slate-400";
      cardSub.textContent =
        product.niche +
        " \u00b7 " +
        (product.price === null || product.price === undefined
          ? "no price"
          : formatPrice(product.price));
      cardTitle.appendChild(cardH);
      cardTitle.appendChild(cardSub);
      cardTop.appendChild(cardTitle);
      var badgeSpan = document.createElement("span");
      badgeSpan.innerHTML = window.statusBadge(product.status);
      cardTop.appendChild(badgeSpan);
      card.appendChild(cardTop);
      card.appendChild(tagChips(product.tags));
      var cardActions = document.createElement("div");
      cardActions.className = "mt-3";
      cardActions.appendChild(actionButtons(product));
      card.appendChild(cardActions);
      cards.appendChild(card);
    });
  }

  /**
   * Load products for the current state, toggling view states.
   */
  async function loadProducts() {
    var loading = document.getElementById("products-loading");
    var errorBox = document.getElementById("products-error");
    var empty = document.getElementById("products-empty");
    var tableWrap = document.getElementById("products-table-wrap");
    var cards = document.getElementById("products-cards");
    var pagination = document.getElementById("products-pagination");
    loading.classList.remove("hidden");
    errorBox.classList.add("hidden");
    empty.classList.add("hidden");
    tableWrap.classList.add("hidden");
    cards.innerHTML = "";
    var mySeq = ++loadSeq;
    try {
      var data = await window.apiFetch("/api/products?" + queryString());
      if (mySeq !== loadSeq) {
        return;
      }
      state.total = data.total;
      loading.classList.add("hidden");
      if (data.items.length === 0) {
        empty.classList.remove("hidden");
      } else {
        tableWrap.classList.remove("hidden");
        renderProducts(data.items);
      }
      window.renderPagination(
        pagination,
        { total: data.total, skip: state.skip, limit: PAGE_SIZE },
        function (nextSkip) {
          state.skip = nextSkip;
          loadProducts();
        }
      );
    } catch (err) {
      if (mySeq !== loadSeq) {
        return;
      }
      loading.classList.add("hidden");
      document.getElementById("products-error-text").textContent =
        "Could not load products: " + err.message;
      errorBox.classList.remove("hidden");
    }
  }

  /**
   * Load niches into the filter dropdown.
   */
  async function loadNiches() {
    try {
      var niches = await window.apiFetch("/api/products/niches");
      var select = document.getElementById("product-niche");
      niches.forEach(function (niche) {
        var opt = document.createElement("option");
        opt.value = niche;
        opt.textContent = niche;
        select.appendChild(opt);
      });
    } catch (err) {
      window.toast("Could not load niches: " + err.message, "error");
    }
  }

  /**
   * Show an inline field error.
   * @param {string} field - Field base id.
   * @param {string} message - Error message.
   */
  function fieldError(field, message) {
    var el = document.getElementById("product-" + field + "-error");
    if (el) {
      el.textContent = message;
      el.classList.remove("hidden");
    }
  }

  /**
   * Clear all inline field errors.
   */
  function clearFieldErrors() {
    ["title", "niche", "design-url", "mockup-url", "store-url", "price"].forEach(
      function (field) {
        var el = document.getElementById("product-" + field + "-error");
        if (el) {
          el.textContent = "";
          el.classList.add("hidden");
        }
      }
    );
  }

  /**
   * Validate a URL field when non-empty.
   * @param {string} field - Field base id.
   * @param {string} value - Raw value.
   * @returns {boolean} True when valid.
   */
  function validUrl(field, value) {
    if (!value) {
      return true;
    }
    try {
      var parsed = new URL(value);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        fieldError(field, "URL must start with http:// or https://.");
        return false;
      }
      return true;
    } catch (err) {
      fieldError(field, "Enter a valid URL.");
      return false;
    }
  }

  /**
   * Open the product modal for create or edit.
   * @param {Object|null} product - Product to edit, or null to create.
   */
  function openProductModal(product) {
    clearFieldErrors();
    document.getElementById("product-modal-title").textContent = product
      ? "Edit Product"
      : "Add Product";
    document.getElementById("product-id").value = product ? String(product.id) : "";
    document.getElementById("product-delete-btn").classList.toggle("hidden", !product);
    document.getElementById("product-title").value = product ? product.title : "";
    document.getElementById("product-niche-input").value = product ? product.niche : "";
    document.getElementById("product-description").value = product
      ? product.description || ""
      : "";
    document.getElementById("product-design-url").value = product
      ? product.design_url || ""
      : "";
    document.getElementById("product-mockup-url").value = product
      ? product.mockup_url || ""
      : "";
    document.getElementById("product-store-url").value = product
      ? product.store_url || ""
      : "";
    document.getElementById("product-price").value =
      product && product.price !== null && product.price !== undefined
        ? String(product.price)
        : "";
    document.getElementById("product-status-input").value = product
      ? product.status
      : "active";
    document.getElementById("product-tags").value = product
      ? (product.tags || []).join(", ")
      : "";
    window.openModal("product-modal");
  }

  /**
   * Handle product form submission.
   * @param {Event} event - Submit event.
   */
  async function onProductSubmit(event) {
    event.preventDefault();
    clearFieldErrors();
    var btn = document.getElementById("product-save");
    var title = document.getElementById("product-title").value.trim();
    var niche = document.getElementById("product-niche-input").value.trim();
    var description = document.getElementById("product-description").value.trim();
    var designUrl = document.getElementById("product-design-url").value.trim();
    var mockupUrl = document.getElementById("product-mockup-url").value.trim();
    var storeUrl = document.getElementById("product-store-url").value.trim();
    var priceRaw = document.getElementById("product-price").value.trim();
    var statusValue = document.getElementById("product-status-input").value;
    var tagsRaw = document.getElementById("product-tags").value;
    var ok = true;
    if (!title) {
      fieldError("title", "Title is required.");
      ok = false;
    }
    if (!niche) {
      fieldError("niche", "Niche is required.");
      ok = false;
    }
    ok = validUrl("design-url", designUrl) && ok;
    ok = validUrl("mockup-url", mockupUrl) && ok;
    ok = validUrl("store-url", storeUrl) && ok;
    var price = null;
    if (priceRaw) {
      price = Number(priceRaw);
      if (Number.isNaN(price) || price < 0) {
        fieldError("price", "Price must be a number >= 0.");
        ok = false;
      }
    }
    if (!ok) {
      return;
    }
    var payload = {
      title: title,
      niche: niche,
      description: description || null,
      design_url: designUrl || null,
      mockup_url: mockupUrl || null,
      store_url: storeUrl || null,
      price: price,
      tags: tagsRaw
        .split(",")
        .map(function (tag) {
          return tag.trim();
        })
        .filter(function (tag) {
          return tag.length > 0;
        }),
      status: statusValue
    };
    var productId = document.getElementById("product-id").value;
    window.setButtonLoading(btn, true, "Saving\u2026");
    try {
      if (productId) {
        await window.apiFetch("/api/products/" + productId, {
          method: "PATCH",
          body: JSON.stringify(payload)
        });
        window.toast("Product updated.", "success");
      } else {
        await window.apiFetch("/api/products", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        window.toast("Product created.", "success");
      }
      window.closeModal("product-modal");
      state.skip = 0;
      loadProducts();
      loadNichesRefresh();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Refresh the niche filter options without duplicates.
   */
  async function loadNichesRefresh() {
    var select = document.getElementById("product-niche");
    var current = select.value;
    select.innerHTML = "";
    var all = document.createElement("option");
    all.value = "";
    all.textContent = "All niches";
    select.appendChild(all);
    await loadNiches();
    select.value = current;
  }

  /**
   * Handle clicks on row action buttons via delegation.
   * @param {Event} event - Click event.
   */
  async function onActionsClick(event) {
    var btn = event.target.closest("button[data-action]");
    if (!btn) {
      return;
    }
    var id = btn.dataset.id;
    var action = btn.dataset.action;
    if (action === "generate") {
      window.location.href = "/studio?product_id=" + encodeURIComponent(id);
      return;
    }
    if (action === "edit") {
      try {
        var product = await window.apiFetch("/api/products/" + id);
        openProductModal(product);
      } catch (err) {
        window.toast(err.message, "error");
      }
      return;
    }
    if (action === "toggle") {
      window.setButtonLoading(btn, true, "Saving\u2026");
      try {
        var current = await window.apiFetch("/api/products/" + id);
        var next = current.status === "active" ? "archived" : "active";
        await window.apiFetch("/api/products/" + id, {
          method: "PATCH",
          body: JSON.stringify({ status: next })
        });
        window.toast("Product " + next + ".", "success");
        loadProducts();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
      return;
    }
  }

  /**
   * Open the details/edit modal when a row or card itself is clicked.
   * Button clicks are handled by onActionsClick and ignored here.
   * @param {Event} event - Click event.
   */
  async function onRowClick(event) {
    if (event.target.closest("button")) {
      return;
    }
    var holder = event.target.closest("tr[data-id], div[data-id]");
    if (!holder) {
      return;
    }
    try {
      var product = await window.apiFetch("/api/products/" + holder.dataset.id);
      openProductModal(product);
    } catch (err) {
      window.toast(err.message, "error");
    }
  }

  /**
   * Delete the product currently open in the modal after confirmation.
   */
  async function onModalDelete(event) {
    var btn = event.currentTarget;
    var id = document.getElementById("product-id").value;
    if (!id) {
      return;
    }
    var confirmed = await window.confirmDialog(
      "Are you sure you want to delete this product?",
      { confirmText: "Delete", danger: true }
    );
    if (!confirmed) {
      return;
    }
    window.setButtonLoading(btn, true, "Deleting\u2026");
    try {
      await window.apiFetch("/api/products/" + id, {
        method: "DELETE",
        headers: { "X-Confirm-Delete": "true" }
      });
      window.toast("Product deleted.", "success");
      window.closeModal("product-modal");
      state.skip = 0;
      loadProducts();
      loadNichesRefresh();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var search = document.getElementById("product-search");
    search.addEventListener(
      "input",
      window.debounce(function () {
        state.search = search.value.trim();
        state.skip = 0;
        loadProducts();
      }, 400)
    );
    document.getElementById("product-niche").addEventListener("change", function (event) {
      state.niche = event.target.value;
      state.skip = 0;
      loadProducts();
    });
    document.getElementById("product-status").addEventListener("change", function (event) {
      state.status = event.target.value;
      state.skip = 0;
      loadProducts();
    });
    document.getElementById("product-add-btn").addEventListener("click", function () {
      openProductModal(null);
    });
    document.getElementById("product-delete-btn").addEventListener("click", onModalDelete);
    document.getElementById("products-empty-add").addEventListener("click", function () {
      openProductModal(null);
    });
    document.getElementById("products-retry").addEventListener("click", loadProducts);
    document.getElementById("product-form").addEventListener("submit", onProductSubmit);
    document.getElementById("product-cancel").addEventListener("click", function () {
      window.closeModal("product-modal");
    });
    document
      .getElementById("products-table-wrap")
      .addEventListener("click", onActionsClick);
    document.getElementById("products-cards").addEventListener("click", onActionsClick);
    document.getElementById("products-tbody").addEventListener("click", onRowClick);
    document.getElementById("products-cards").addEventListener("click", onRowClick);
    loadProducts();
    loadNiches();
  });
})();
