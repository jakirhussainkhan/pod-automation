/* Posts page: cards, filters, edit/schedule/duplicate/regenerate. */
(function () {
  "use strict";

  var PAGE_SIZE = 10;
  var state = { skip: 0, total: 0, status: "", productId: "" };
  var selected = {};
  var pageIds = [];
  var productNames = {};
  var facebookStatus = null;

  /**
   * Load the Facebook connection status once for confirm dialogs.
   */
  async function loadFacebookStatus() {
    try {
      facebookStatus = await window.apiFetch("/api/facebook/status");
    } catch (err) {
      facebookStatus = null;
    }
  }

  /**
   * Split a hashtags input on commas or whitespace and prefix with #.
   * @param {string} raw - Raw input.
   * @returns {Array<string>} Cleaned tags.
   */
  function parseHashtags(raw) {
    var tags = [];
    String(raw || "")
      .split(/[\s,]+/)
      .forEach(function (part) {
        var tag = part.trim();
        if (!tag) {
          return;
        }
        if (tag.charAt(0) !== "#") {
          tag = "#" + tag;
        }
        if (tag.length > 1) {
          tags.push(tag);
        }
      });
    return tags;
  }

  /**
   * Build hashtag chips.
   * @param {Array<string>} tags - Tags.
   * @returns {HTMLElement} Chips container.
   */
  function hashtagChips(tags) {
    var wrap = document.createElement("div");
    wrap.className = "flex flex-wrap gap-1 mt-2";
    (tags || []).forEach(function (tag) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = tag;
      wrap.appendChild(chip);
    });
    return wrap;
  }

  /**
   * Build a meta line element.
   * @param {string} label - Label text.
   * @param {string} value - Value text.
   * @returns {HTMLElement|null} Meta paragraph or null when empty.
   */
  function metaLine(label, value) {
    if (!value) {
      return null;
    }
    var p = document.createElement("p");
    p.className = "text-xs text-gray-500 dark:text-slate-400 mt-1";
    var strong = document.createElement("span");
    strong.className = "font-semibold";
    strong.textContent = label + ": ";
    var span = document.createElement("span");
    span.textContent = value;
    p.appendChild(strong);
    p.appendChild(span);
    return p;
  }

  /**
   * Build action buttons allowed for a post status.
   * @param {Object} post - Post record.
   * @returns {HTMLElement} Actions container.
   */
  function actionButtons(post) {
    var wrap = document.createElement("div");
    wrap.className = "flex flex-wrap gap-2 mt-3";
    var actions = [];
    if (post.status === "published") {
      actions = [
        { label: "Duplicate", name: "duplicate", cls: "btn-secondary" },
        { label: "Delete", name: "delete", cls: "btn-danger" }
      ];
    } else if (post.status === "scheduled") {
      actions = [
        { label: "Publish Now", name: "publish", cls: "btn-primary" },
        { label: "Edit", name: "edit", cls: "btn-secondary" },
        { label: "Unschedule", name: "unschedule", cls: "btn-secondary" },
        { label: "Duplicate", name: "duplicate", cls: "btn-secondary" },
        { label: "Delete", name: "delete", cls: "btn-danger" }
      ];
    } else {
      actions = [
        { label: "Publish Now", name: "publish", cls: "btn-primary" },
        { label: "Edit", name: "edit", cls: "btn-secondary" },
        { label: "Schedule", name: "schedule", cls: "btn-secondary" },
        { label: "Regenerate", name: "regenerate", cls: "btn-secondary" },
        { label: "Duplicate", name: "duplicate", cls: "btn-secondary" },
        { label: "Delete", name: "delete", cls: "btn-danger" }
      ];
    }
    actions.forEach(function (action) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm " + action.cls;
      btn.textContent = action.label;
      btn.dataset.action = action.name;
      btn.dataset.id = String(post.id);
      wrap.appendChild(btn);
    });
    return wrap;
  }

  /**
   * Render a single post card.
   * @param {Object} post - Post record.
   * @returns {HTMLElement} Card element.
   */
  function postCard(post) {
    var card = document.createElement("article");
    card.className = "bg-white/70 dark:bg-slate-900/60 backdrop-blur-md border border-gray-200/60 dark:border-slate-700/50 rounded-xl shadow-lg shadow-gray-200/50 dark:shadow-xl dark:shadow-black/20 p-4 md:p-5";
    card.dataset.postId = String(post.id);
    var head = document.createElement("div");
    head.className = "flex items-start gap-3";
    var selectBox = document.createElement("input");
    selectBox.type = "checkbox";
    selectBox.className = "mt-1 h-4 w-4 flex-shrink-0";
    selectBox.checked = !!selected[post.id];
    selectBox.setAttribute("aria-label", "Select post " + post.id);
    selectBox.addEventListener("change", function () {
      if (selectBox.checked) {
        selected[post.id] = true;
      } else {
        delete selected[post.id];
      }
      renderBulkBar();
    });
    head.appendChild(selectBox);
    if (post.image_url) {
      var img = document.createElement("img");
      img.src = post.image_url;
      img.alt = "Post image";
      img.className = "w-16 h-16 rounded-lg object-cover flex-shrink-0";
      img.loading = "lazy";
      window.guardImage(img);
      head.appendChild(img);
    }
    var headMain = document.createElement("div");
    headMain.className = "min-w-0 flex-1";
    var titleRow = document.createElement("div");
    titleRow.className = "flex flex-wrap items-center gap-2";
    var title = document.createElement("h3");
    title.className = "font-semibold text-gray-900 dark:text-slate-100";
    title.textContent = post.product_id && productNames[post.product_id]
      ? productNames[post.product_id]
      : "Post " + post.id;
    var badge = document.createElement("span");
    badge.innerHTML = window.statusBadge(post.status);
    titleRow.appendChild(title);
    titleRow.appendChild(badge);
    headMain.appendChild(titleRow);
    var caption = document.createElement("p");
    caption.className = "text-sm text-gray-700 dark:text-slate-200 mt-2 clamp-4";
    caption.textContent = post.caption;
    headMain.appendChild(caption);
    if (post.caption && post.caption.length > 160) {
      var more = document.createElement("button");
      more.type = "button";
      more.className = "text-xs text-blue-600 dark:text-blue-400 font-medium hover:underline mt-1";
      more.textContent = "Read more";
      more.setAttribute("aria-expanded", "false");
      more.addEventListener("click", function () {
        var expanded = caption.classList.toggle("clamp-4");
        more.textContent = expanded ? "Read more" : "Show less";
        more.setAttribute("aria-expanded", expanded ? "false" : "true");
      });
      headMain.appendChild(more);
    }
    headMain.appendChild(hashtagChips(post.hashtags));
    head.appendChild(headMain);
    card.appendChild(head);

    var meta = document.createElement("div");
    meta.className = "mt-2";
    var scheduled = post.scheduled_at ? window.formatDate(post.scheduled_at) : "";
    var published = post.published_at ? window.formatDate(post.published_at) : "";
    [
      metaLine("Scheduled", scheduled === "\u2014" ? "" : scheduled),
      metaLine("Published", published === "\u2014" ? "" : published),
      metaLine("Facebook ID", post.facebook_post_id || ""),
      metaLine(
        "AI",
        post.ai_provider ? post.ai_provider + " \u00b7 " + (post.ai_model || "") : ""
      )
    ].forEach(function (line) {
      if (line) {
        meta.appendChild(line);
      }
    });
    if (post.status === "failed" && post.error_message) {
      var err = document.createElement("p");
      err.className = "text-xs text-red-600 dark:text-red-400 mt-1";
      err.textContent = post.error_message;
      meta.appendChild(err);
      var attempts = document.createElement("p");
      attempts.className = "text-xs text-gray-500 dark:text-slate-400 mt-1";
      attempts.textContent = "Attempts: " + String(post.publish_attempts || 0);
      meta.appendChild(attempts);
    }
    card.appendChild(meta);
    card.appendChild(actionButtons(post));
    return card;
  }

  /**
   * Render status tabs with counts from dashboard stats.
   * @param {Object} byStatus - Counts per status.
   */
  function renderTabs(byStatus) {
    var tabs = document.getElementById("status-tabs");
    tabs.innerHTML = "";
    var defs = [
      { value: "", label: "All" },
      { value: "draft", label: "Draft" },
      { value: "scheduled", label: "Scheduled" },
      { value: "published", label: "Published" },
      { value: "failed", label: "Failed" }
    ];
    defs.forEach(function (def) {
      var btn = document.createElement("button");
      btn.type = "button";
      var count = def.value === "" ? null : byStatus[def.value];
      btn.textContent = count === null ? def.label : def.label + " (" + count + ")";
      btn.className = "pill" + (state.status === def.value ? " pill-active" : "");
      btn.setAttribute("aria-pressed", state.status === def.value ? "true" : "false");
      btn.addEventListener("click", function () {
        state.status = def.value;
        state.skip = 0;
        loadPosts();
        renderTabs(byStatus);
      });
      tabs.appendChild(btn);
    });
  }

  /**
   * Refresh the bulk action bar from the current selection and filter.
   */
  function renderBulkBar() {
    var bar = document.getElementById("posts-bulkbar");
    var countLabel = document.getElementById("posts-selected-count");
    var deleteBtn = document.getElementById("posts-bulk-delete");
    var clearLabel = document.getElementById("posts-clear-all-label");
    var selectAll = document.getElementById("posts-select-all");
    if (!bar) {
      return;
    }
    var ids = Object.keys(selected);
    var scope = state.status
      ? state.status.charAt(0).toUpperCase() + state.status.slice(1)
      : "Posts";
    bar.classList.remove("hidden");
    countLabel.textContent = ids.length + " selected";
    deleteBtn.disabled = ids.length === 0;
    deleteBtn.textContent = ids.length > 0 ? "Delete Selected (" + ids.length + ")" : "Delete Selected";
    clearLabel.textContent = state.status ? scope + "s" : "All Posts";
    if (selectAll) {
      selectAll.checked = pageIds.length > 0 && pageIds.every(function (id) {
        return !!selected[id];
      });
    }
  }

  /**
   * Reload posts and tab counts after a destructive bulk action.
   */
  function refreshAfterBulk() {
    selected = {};
    state.skip = 0;
    loadPosts();
    loadFilters();
  }

  /**
   * Delete all currently selected posts after confirmation.
   * @param {HTMLButtonElement} btn - Trigger button.
   */
  async function onBulkDelete(btn) {
    var ids = Object.keys(selected).map(Number);
    if (ids.length === 0) {
      return;
    }
    var confirmed = await window.confirmDialog(
      "Are you sure you want to delete " + ids.length + " selected post(s)?",
      { confirmText: "Delete Selected", danger: true }
    );
    if (!confirmed) {
      return;
    }
    window.setButtonLoading(btn, true, "Deleting…");
    try {
      var result = await window.apiFetch("/api/posts/bulk-delete", {
        method: "POST",
        headers: { "X-Confirm-Delete": "true" },
        body: JSON.stringify({ ids: ids })
      });
      window.toast("Deleted " + result.deleted + " post(s).", "success");
      refreshAfterBulk();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Delete every post in the current filter scope after confirmation.
   * @param {HTMLButtonElement} btn - Trigger button.
   */
  async function onClearAll(btn) {
    var scope = state.status ? state.status + " posts" : "ALL posts";
    var confirmed = await window.confirmDialog(
      "Are you sure you want to delete " + scope + " (" + state.total + " total)? This cannot be undone.",
      { confirmText: "Delete All", danger: true }
    );
    if (!confirmed) {
      return;
    }
    window.setButtonLoading(btn, true, "Deleting…");
    try {
      var payload = { delete_all: true, confirm: true };
      if (state.status) {
        payload.status = state.status;
      }
      var result = await window.apiFetch("/api/posts/bulk-delete", {
        method: "POST",
        headers: { "X-Confirm-Delete": "true" },
        body: JSON.stringify(payload)
      });
      window.toast("Deleted " + result.deleted + " post(s).", "success");
      refreshAfterBulk();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Load posts for the current filters.
   */
  async function loadPosts() {
    var loading = document.getElementById("posts-loading");
    var errorBox = document.getElementById("posts-error");
    var empty = document.getElementById("posts-empty");
    var list = document.getElementById("posts-list");
    var pagination = document.getElementById("posts-pagination");
    loading.classList.remove("hidden");
    errorBox.classList.add("hidden");
    empty.classList.add("hidden");
    list.innerHTML = "";
    var params = new URLSearchParams();
    params.set("skip", String(state.skip));
    params.set("limit", String(PAGE_SIZE));
    if (state.status) {
      params.set("status", state.status);
    }
    if (state.productId) {
      params.set("product_id", state.productId);
    }
    try {
      var data = await window.apiFetch("/api/posts?" + params.toString());
      state.total = data.total;
      loading.classList.add("hidden");
      pageIds = data.items.map(function (post) {
        return post.id;
      });
      if (data.items.length === 0) {
        empty.classList.remove("hidden");
      } else {
        data.items.forEach(function (post) {
          list.appendChild(postCard(post));
        });
      }
      renderBulkBar();
      window.renderPagination(
        pagination,
        { total: data.total, skip: state.skip, limit: PAGE_SIZE },
        function (nextSkip) {
          state.skip = nextSkip;
          loadPosts();
        }
      );
    } catch (err) {
      loading.classList.add("hidden");
      document.getElementById("posts-error-text").textContent =
        "Could not load posts: " + err.message;
      errorBox.classList.remove("hidden");
    }
  }

  /**
   * Load tab counts and product dropdowns.
   */
  async function loadFilters() {
    try {
      var stats = await window.apiFetch("/api/dashboard/stats");
      renderTabs(stats.posts_by_status || {});
    } catch (err) {
      renderTabs({});
    }
    try {
      var data = await window.apiFetch("/api/products?skip=0&limit=100");
      var filter = document.getElementById("post-product-filter");
      var select = document.getElementById("post-product");
      data.items.forEach(function (product) {
        productNames[product.id] = product.title;
        var opt1 = document.createElement("option");
        opt1.value = String(product.id);
        opt1.textContent = product.title;
        filter.appendChild(opt1);
        var opt2 = document.createElement("option");
        opt2.value = String(product.id);
        opt2.textContent = product.title;
        select.appendChild(opt2);
      });
    } catch (err) {
      window.toast("Could not load products: " + err.message, "error");
    }
  }

  /**
   * Open the create/edit modal.
   * @param {Object|null} post - Post to edit, or null to create.
   */
  function openPostModal(post) {
    document.getElementById("post-modal-title").textContent = post ? "Edit Post" : "New Post";
    document.getElementById("post-id").value = post ? String(post.id) : "";
    document.getElementById("post-product").value = post && post.product_id ? String(post.product_id) : "";
    document.getElementById("post-caption").value = post ? post.caption : "";
    document.getElementById("post-hashtags").value = post ? (post.hashtags || []).join(" ") : "";
    document.getElementById("post-image-url").value = post ? post.image_url || "" : "";
    updateCaptionCount();
    window.openModal("post-modal");
  }

  /**
   * Update the live caption character count.
   */
  function updateCaptionCount() {
    document.getElementById("post-caption-count").textContent = String(
      document.getElementById("post-caption").value.length
    );
  }

  /**
   * Handle post form submission.
   * @param {Event} event - Submit event.
   */
  async function onPostSubmit(event) {
    event.preventDefault();
    var btn = document.getElementById("post-save");
    var captionError = document.getElementById("post-caption-error");
    var imageError = document.getElementById("post-image-url-error");
    captionError.classList.add("hidden");
    imageError.classList.add("hidden");
    var caption = document.getElementById("post-caption").value;
    var imageUrl = document.getElementById("post-image-url").value.trim();
    if (!caption.trim()) {
      captionError.textContent = "Caption is required.";
      captionError.classList.remove("hidden");
      return;
    }
    if (imageUrl) {
      try {
        var parsed = new URL(imageUrl);
        if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
          throw new Error("bad protocol");
        }
      } catch (err) {
        imageError.textContent = "Enter a valid URL.";
        imageError.classList.remove("hidden");
        return;
      }
    }
    var productRaw = document.getElementById("post-product").value;
    var payload = {
      product_id: productRaw ? Number(productRaw) : null,
      caption: caption,
      hashtags: parseHashtags(document.getElementById("post-hashtags").value),
      image_url: imageUrl || null
    };
    var postId = document.getElementById("post-id").value;
    window.setButtonLoading(btn, true, "Saving\u2026");
    try {
      if (postId) {
        await window.apiFetch("/api/posts/" + postId, {
          method: "PATCH",
          body: JSON.stringify(payload)
        });
        window.toast("Post updated.", "success");
      } else {
        await window.apiFetch("/api/posts", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        window.toast("Post created.", "success");
      }
      window.closeModal("post-modal");
      state.skip = 0;
      loadPosts();
      loadFilters();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Open the schedule modal for a post.
   * @param {string} postId - Post id.
   */
  function openScheduleModal(postId) {
    document.getElementById("schedule-post-id").value = postId;
    var input = document.getElementById("schedule-at");
    var now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    input.min = now.toISOString().slice(0, 16);
    input.value = "";
    document.getElementById("schedule-tz").textContent =
      Intl.DateTimeFormat().resolvedOptions().timeZone;
    document.getElementById("schedule-at-error").classList.add("hidden");
    window.openModal("schedule-modal");
  }

  /**
   * Handle schedule form submission.
   * @param {Event} event - Submit event.
   */
  async function onScheduleSubmit(event) {
    event.preventDefault();
    var btn = document.getElementById("schedule-save");
    var error = document.getElementById("schedule-at-error");
    error.classList.add("hidden");
    var raw = document.getElementById("schedule-at").value;
    if (!raw) {
      error.textContent = "Pick a date and time.";
      error.classList.remove("hidden");
      return;
    }
    var iso = new Date(raw).toISOString();
    var postId = document.getElementById("schedule-post-id").value;
    window.setButtonLoading(btn, true, "Scheduling\u2026");
    try {
      await window.apiFetch("/api/posts/" + postId + "/schedule", {
        method: "POST",
        body: JSON.stringify({ scheduled_at: iso })
      });
      window.toast("Post scheduled.", "success");
      window.closeModal("schedule-modal");
      loadPosts();
      loadFilters();
    } catch (err) {
      error.textContent = err.message;
      error.classList.remove("hidden");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Handle regenerate form submission.
   * @param {Event} event - Submit event.
   */
  async function onRegenerateSubmit(event) {
    event.preventDefault();
    var btn = document.getElementById("regenerate-save");
    var postId = document.getElementById("regenerate-post-id").value;
    var tone = document.getElementById("regenerate-tone").value;
    window.setButtonLoading(btn, true, "Regenerating\u2026");
    try {
      await window.apiFetch("/api/ai/posts/" + postId + "/regenerate-caption", {
        method: "POST",
        body: JSON.stringify({ tone: tone })
      });
      window.toast("Caption regenerated.", "success");
      window.closeModal("regenerate-modal");
      loadPosts();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Handle card action clicks via delegation.
   * @param {Event} event - Click event.
   */
  async function onActionsClick(event) {
    var btn = event.target.closest("button[data-action]");
    if (!btn || btn.disabled) {
      return;
    }
    var id = btn.dataset.id;
    var action = btn.dataset.action;
    if (action === "edit") {
      try {
        var post = await window.apiFetch("/api/posts/" + id);
        openPostModal(post);
      } catch (err) {
        window.toast(err.message, "error");
      }
      return;
    }
    if (action === "schedule") {
      openScheduleModal(id);
      return;
    }
    if (action === "publish") {
      var dryNote =
        facebookStatus && facebookStatus.dry_run
          ? " Dry-run mode: nothing will be posted."
          : "";
      var confirmedPublish = await window.confirmDialog(
        "Publish post " + id + " now?" + dryNote,
        { confirmText: "Publish Now" }
      );
      if (!confirmedPublish) {
        return;
      }
      window.setButtonLoading(btn, true, "Publishing\u2026");
      try {
        var published = await window.apiFetch("/api/posts/" + id + "/publish", {
          method: "POST"
        });
        window.toast(
          "Post published (" + (published.facebook_post_id || "ok") + ").",
          "success"
        );
        loadPosts();
        loadFilters();
      } catch (err) {
        if (err && err.status === 401) {
          window.toast("Facebook token invalid or expired. Update it in .env.", "error");
        } else if (err && err.status === 429) {
          window.toast("Facebook rate limit hit. Try again later.", "error");
        } else {
          window.toast(err.message, "error");
        }
      } finally {
        window.setButtonLoading(btn, false);
      }
      return;
    }
    if (action === "regenerate") {
      document.getElementById("regenerate-post-id").value = id;
      window.openModal("regenerate-modal");
      return;
    }
    if (action === "duplicate") {
      window.setButtonLoading(btn, true, "Duplicating\u2026");
      try {
        await window.apiFetch("/api/posts/" + id + "/duplicate", { method: "POST" });
        window.toast("Post duplicated as draft.", "success");
        loadPosts();
        loadFilters();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
      return;
    }
    if (action === "unschedule") {
      window.setButtonLoading(btn, true, "Working\u2026");
      try {
        await window.apiFetch("/api/posts/" + id + "/unschedule", { method: "POST" });
        window.toast("Post unscheduled.", "success");
        loadPosts();
        loadFilters();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
      return;
    }
    if (action === "delete") {
      var confirmed = await window.confirmDialog(
        "Are you sure you want to delete this post?",
        { confirmText: "Delete", danger: true }
      );
      if (!confirmed) {
        return;
      }
      window.setButtonLoading(btn, true, "Deleting\u2026");
      try {
        await window.apiFetch("/api/posts/" + id, { method: "DELETE" });
        delete selected[id];
        window.toast("Post deleted.", "success");
        loadPosts();
        loadFilters();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("post-product-filter").addEventListener("change", function (e) {
      state.productId = e.target.value;
      state.skip = 0;
      loadPosts();
    });
    document.getElementById("post-new-btn").addEventListener("click", function () {
      openPostModal(null);
    });
    document.getElementById("posts-empty-new").addEventListener("click", function () {
      openPostModal(null);
    });
    document.getElementById("posts-retry").addEventListener("click", loadPosts);
    document.getElementById("post-form").addEventListener("submit", onPostSubmit);
    document.getElementById("post-caption").addEventListener("input", updateCaptionCount);
    document.getElementById("post-cancel").addEventListener("click", function () {
      window.closeModal("post-modal");
    });
    document.getElementById("schedule-form").addEventListener("submit", onScheduleSubmit);
    document.getElementById("schedule-cancel").addEventListener("click", function () {
      window.closeModal("schedule-modal");
    });
    document.getElementById("regenerate-form").addEventListener("submit", onRegenerateSubmit);
    document.getElementById("regenerate-cancel").addEventListener("click", function () {
      window.closeModal("regenerate-modal");
    });
    document.getElementById("posts-list").addEventListener("click", onActionsClick);
    document.getElementById("posts-select-all").addEventListener("change", function (event) {
      var checked = event.target.checked;
      pageIds.forEach(function (id) {
        if (checked) {
          selected[id] = true;
        } else {
          delete selected[id];
        }
      });
      loadPosts();
    });
    document.getElementById("posts-bulk-delete").addEventListener("click", function (event) {
      onBulkDelete(event.currentTarget);
    });
    document.getElementById("posts-clear-all").addEventListener("click", function (event) {
      onClearAll(event.currentTarget);
    });
    loadPosts();
    loadFilters();
    loadFacebookStatus();
  });
})();
