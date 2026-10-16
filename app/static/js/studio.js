/* AI Studio page: preview, variations, hashtags, save as draft. */
(function () {
  "use strict";

  var state = { tone: "friendly", lastRun: null };
  var genSeq = 0;

  /**
   * Read the selected product id.
   * @returns {number|null} Product id or null.
   */
  function selectedProductId() {
    var value = document.getElementById("studio-product").value;
    return value ? Number(value) : null;
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
   * Build a result card for generated content.
   * @param {Object} content - Generated content payload.
   * @returns {HTMLElement} Card element.
   */
  function resultCard(content) {
    var card = document.createElement("article");
    card.className = "bg-white/70 dark:bg-slate-900/60 backdrop-blur-md border border-gray-200/60 dark:border-slate-700/50 rounded-xl shadow-lg shadow-gray-200/50 dark:shadow-xl dark:shadow-black/20 p-4 md:p-5";
    var badge = document.createElement("div");
    badge.className = "mb-2 text-xs text-gray-500 dark:text-slate-400";
    var provider = document.createElement("span");
    provider.className = "badge badge-gray";
    provider.textContent = (content.provider || "unknown") + " \u00b7 " + (content.model || "");
    badge.appendChild(provider);
    card.appendChild(badge);
    var caption = document.createElement("p");
    caption.className = "text-sm text-gray-800 dark:text-slate-100 whitespace-pre-wrap";
    caption.textContent = content.caption;
    card.appendChild(caption);
    card.appendChild(hashtagChips(content.hashtags));
    if (content.call_to_action) {
      var cta = document.createElement("p");
      cta.className = "text-sm mt-2 text-gray-900 dark:text-slate-100";
      var ctaLabel = document.createElement("span");
      ctaLabel.className = "font-semibold";
      ctaLabel.textContent = "Call to action: ";
      var ctaText = document.createElement("span");
      ctaText.textContent = content.call_to_action;
      cta.appendChild(ctaLabel);
      cta.appendChild(ctaText);
      card.appendChild(cta);
    }
    if (content.image_idea) {
      var idea = document.createElement("p");
      idea.className = "text-sm mt-1 text-gray-600 dark:text-slate-300";
      var ideaLabel = document.createElement("span");
      ideaLabel.className = "font-semibold";
      ideaLabel.textContent = "Image idea: ";
      var ideaText = document.createElement("span");
      ideaText.textContent = content.image_idea;
      idea.appendChild(ideaLabel);
      idea.appendChild(ideaText);
      card.appendChild(idea);
    }
    var actions = document.createElement("div");
    actions.className = "flex flex-wrap gap-2 mt-4";
    [
      { label: "Copy Caption", name: "copy-caption", cls: "btn-secondary" },
      { label: "Copy Hashtags", name: "copy-hashtags", cls: "btn-secondary" },
      { label: "Save as Draft", name: "save-draft", cls: "btn-primary" }
    ].forEach(function (action) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm " + action.cls;
      btn.textContent = action.label;
      btn.dataset.action = action.name;
      actions.appendChild(btn);
    });
    card.appendChild(actions);
    card._content = content;
    return card;
  }

  /**
   * Render generated content items.
   * @param {Array<Object>} items - Content payloads.
   */
  function renderResults(items) {
    var results = document.getElementById("studio-results");
    var empty = document.getElementById("studio-empty");
    results.innerHTML = "";
    if (!items || items.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    items.forEach(function (item) {
      results.appendChild(resultCard(item));
    });
  }

  /**
   * Show a generation error with mapped messaging.
   * @param {Error} err - Fetch error.
   */
  function showError(err) {
    var box = document.getElementById("studio-error");
    var text = document.getElementById("studio-error-text");
    if (err && err.status === 503) {
      text.textContent = "No AI provider configured. Add an API key in .env or enable AI_MOCK_MODE.";
    } else if (err && err.status === 502) {
      text.textContent = "The AI provider failed. Try again.";
    } else {
      text.textContent = err ? err.message : "Generation failed.";
    }
    box.classList.remove("hidden");
  }

  /**
   * Run an AI action with loading state and error handling.
   * @param {HTMLButtonElement} btn - Trigger button.
   * @param {Function} fn - Async work returning result items.
   */
  async function runAction(btn, fn) {
    var loading = document.getElementById("studio-loading");
    var mySeq = ++genSeq;
    document.getElementById("studio-error").classList.add("hidden");
    loading.classList.remove("hidden");
    // Remember the last action so the Retry button can re-run it.
    state.lastRun = { btn: btn, fn: fn };
    window.setButtonLoading(btn, true, "Generating\u2026");
    try {
      var items = await fn();
      if (mySeq !== genSeq) {
        return;
      }
      // A null result means "handled elsewhere" (e.g. group panel) — leave the
      // studio results/empty state untouched instead of flashing "no results".
      if (items !== null) {
        renderResults(items);
      }
    } catch (err) {
      if (mySeq !== genSeq) {
        return;
      }
      showError(err);
    } finally {
      window.setButtonLoading(btn, false);
      if (mySeq === genSeq) {
        loading.classList.add("hidden");
      }
    }
  }

  /**
   * Handle result card action clicks via delegation.
   * @param {Event} event - Click event.
   */
  async function onResultClick(event) {
    var btn = event.target.closest("button[data-action]");
    if (!btn || btn.disabled) {
      return;
    }
    var card = btn.closest("article");
    var content = card ? card._content : null;
    if (!content) {
      return;
    }
    var action = btn.dataset.action;
    if (action === "copy-caption") {
      var ok = await window.copyToClipboard(content.caption);
      window.toast(ok ? "Caption copied." : "Copy failed.", ok ? "success" : "error");
      return;
    }
    if (action === "copy-hashtags") {
      var done = await window.copyToClipboard((content.hashtags || []).join(" "));
      window.toast(done ? "Hashtags copied." : "Copy failed.", done ? "success" : "error");
      return;
    }
    if (action === "save-draft") {
      var productId = selectedProductId();
      if (!productId) {
        window.toast("Select a product first.", "error");
        return;
      }
      window.setButtonLoading(btn, true, "Saving\u2026");
      try {
        var post = await window.apiFetch("/api/posts", {
          method: "POST",
          body: JSON.stringify({
            product_id: productId,
            caption: content.caption,
            hashtags: content.hashtags || []
          })
        });
        window.toast("Draft post " + post.id + " saved.", "success");
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
    }
  }

  /**
   * Queue post text (caption + hashtags) for clipboard copy.
   * @param {Object} item - Queue item payload.
   * @returns {string} Full post text.
   */
  function queueFullText(item) {
    var tags = (item.hashtags || []).join(" ");
    return item.caption + (tags ? "\n\n" + tags : "");
  }

  /**
   * Load the Group Post Queue into the sidebar list.
   */
  async function loadQueue() {
    var list = document.getElementById("queue-list");
    var empty = document.getElementById("queue-empty");
    var counts = document.getElementById("queue-counts");
    if (!list) {
      return;
    }
    try {
      var data = await window.apiFetch("/api/groups/queue");
      list.innerHTML = "";
      if (counts) {
        counts.textContent = (data.queued || 0) + " queued · " + (data.posted || 0) + " posted";
      }
      if (!data.items || data.items.length === 0) {
        if (empty) {
          empty.classList.remove("hidden");
        }
        return;
      }
      if (empty) {
        empty.classList.add("hidden");
      }
      data.items.forEach(function (item) {
        list.appendChild(queueCard(item));
      });
    } catch (err) {
      window.toast("Could not load post queue: " + err.message, "error");
    }
  }

  /**
   * Build a queue card with view/edit/copy & mark posted actions.
   * @param {Object} item - Queue item payload.
   * @returns {HTMLElement} Card element.
   */
  function queueCard(item) {
    var card = document.createElement("article");
    card.className = "bg-white/70 dark:bg-slate-900/60 backdrop-blur-md border border-gray-200/60 dark:border-slate-700/50 rounded-xl shadow-lg shadow-gray-200/50 dark:shadow-xl dark:shadow-black/20 p-4";
    card.dataset.queueId = String(item.id);
    var head = document.createElement("div");
    head.className = "flex flex-wrap items-center gap-1 mb-2";
    var status = document.createElement("span");
    status.className = "badge " + (item.status === "posted" ? "badge-green" : "badge-blue");
    status.textContent = item.status === "posted" ? "POSTED" : "QUEUED";
    head.appendChild(status);
    [item.niche, item.template].forEach(function (meta) {
      if (!meta) {
        return;
      }
      var chip = document.createElement("span");
      chip.className = "badge badge-gray";
      chip.textContent = meta;
      head.appendChild(chip);
    });
    card.appendChild(head);
    var caption = document.createElement("p");
    caption.className = "text-sm text-gray-800 dark:text-slate-100 whitespace-pre-wrap clamp-4";
    caption.textContent = item.caption;
    card.appendChild(caption);
    var cta = document.createElement("p");
    cta.className = "text-xs mt-1 text-gray-500 dark:text-slate-400";
    cta.textContent = item.call_to_action || "";
    card.appendChild(cta);
    var actions = document.createElement("div");
    actions.className = "flex flex-wrap gap-1 mt-3";
    function addBtn(label, primary, handler) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm " + (primary ? "btn-primary" : "btn-secondary");
      btn.textContent = label;
      btn.addEventListener("click", handler);
      actions.appendChild(btn);
      return btn;
    }
    addBtn("Copy", false, async function () {
      var ok = await window.copyToClipboard(queueFullText(item));
      window.toast(ok ? "Post text copied." : "Copy failed.", ok ? "success" : "error");
      if (ok) {
        // Best-effort copy tracking for template performance stats.
        window.apiFetch("/api/groups/queue/" + item.id + "/copy", { method: "POST" }).catch(function () {
          /* Tracking must never break copying. */
        });
      }
    });
    if (item.status !== "posted") {
      addBtn("Copy & Mark Posted", true, async function (event) {
        var ok = await window.copyToClipboard(queueFullText(item));
        if (!ok) {
          window.toast("Copy failed.", "error");
          return;
        }
        try {
          await window.apiFetch("/api/groups/queue/" + item.id + "/mark-posted", {
            method: "POST"
          });
          window.toast("Copied — paste into Facebook. Marked as posted.", "success");
          loadQueue();
        } catch (err) {
          window.toast(err.message, "error");
        }
      });
      addBtn("Edit", false, function () {
        openQueueEditModal(item);
      });
    }
    addBtn("Delete", false, async function () {
      var confirmed = await window.confirmDialog("Delete queued post " + item.id + "?", { danger: true, confirmText: "Delete" });
      if (!confirmed) {
        return;
      }
      try {
        await window.apiFetch("/api/groups/queue/" + item.id, { method: "DELETE" });
        window.toast("Queued post deleted.", "success");
        loadQueue();
      } catch (err) {
        window.toast(err.message, "error");
      }
    });
    card.appendChild(actions);
    return card;
  }

  /**
   * Open the shared modal to edit a queued caption.
   * @param {Object} item - Queue item payload.
   */
  function openQueueEditModal(item) {
    document.getElementById("generic-modal-title").textContent = "Edit Queued Post " + item.id;
    var modalBody = document.getElementById("generic-modal-body");
    modalBody.innerHTML = "";
    var label = document.createElement("label");
    label.className = "field-label";
    label.setAttribute("for", "queue-edit-caption");
    label.textContent = "Caption (zero-link enforced on save)";
    var area = document.createElement("textarea");
    area.id = "queue-edit-caption";
    area.className = "field-input";
    area.rows = 6;
    area.value = item.caption;
    var save = document.createElement("button");
    save.type = "button";
    save.className = "btn btn-primary btn-sm mt-3";
    save.textContent = "Save Caption";
    save.addEventListener("click", async function () {
      if (!area.value.trim()) {
        window.toast("Caption cannot be empty.", "error");
        return;
      }
      window.setButtonLoading(save, true, "Saving…");
      try {
        await window.apiFetch("/api/groups/queue/" + item.id, {
          method: "PATCH",
          body: JSON.stringify({ caption: area.value.trim() })
        });
        window.closeModal("generic-modal");
        window.toast("Queued post updated.", "success");
        loadQueue();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(save, false);
      }
    });
    modalBody.appendChild(label);
    modalBody.appendChild(area);
    modalBody.appendChild(save);
    window.openModal("generic-modal");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var params = new URLSearchParams(window.location.search);
    var preselected = params.get("product_id");
    window
      .apiFetch("/api/products?skip=0&limit=100")
      .then(function (data) {
        var select = document.getElementById("studio-product");
        if (data.items.length === 0) {
          var opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "No products yet";
          select.appendChild(opt);
          return;
        }
        data.items.forEach(function (product) {
          var opt = document.createElement("option");
          opt.value = String(product.id);
          opt.textContent = product.title;
          select.appendChild(opt);
        });
        if (preselected) {
          select.value = preselected;
        }
      })
      .catch(function (err) {
        window.toast("Could not load products: " + err.message, "error");
      });

    document.getElementById("studio-tones").addEventListener("click", function (event) {
      var pill = event.target.closest("button[data-tone]");
      if (!pill) {
        return;
      }
      state.tone = pill.dataset.tone;
      Array.prototype.forEach.call(
        document.querySelectorAll("#studio-tones .pill"),
        function (el) {
          el.classList.toggle("pill-active", el === pill);
          el.setAttribute("aria-pressed", el === pill ? "true" : "false");
        }
      );
    });

    document
      .getElementById("studio-preview-btn")
      .addEventListener("click", function (event) {
        var productId = selectedProductId();
        if (!productId) {
          window.toast("Select a product first.", "error");
          return;
        }
        state.lastAction = "preview";
        runAction(event.currentTarget, function () {
          return window
            .apiFetch("/api/ai/preview", {
              method: "POST",
              body: JSON.stringify({ product_id: productId, tone: state.tone })
            })
            .then(function (content) {
              return [content];
            });
        });
      });

    document
      .getElementById("studio-variations-btn")
      .addEventListener("click", function (event) {
        var productId = selectedProductId();
        if (!productId) {
          window.toast("Select a product first.", "error");
          return;
        }
        var count = Number(document.getElementById("studio-count").value) || 3;
        if (count < 2 || count > 5) {
          window.toast("Variation count must be between 2 and 5.", "error");
          return;
        }
        state.lastAction = "variations";
        runAction(event.currentTarget, function () {
          return window.apiFetch("/api/ai/products/" + productId + "/variations", {
            method: "POST",
            body: JSON.stringify({ count: count })
          });
        });
      });

    document
      .getElementById("studio-hashtags-btn")
      .addEventListener("click", function (event) {
        var productId = selectedProductId();
        if (!productId) {
          window.toast("Select a product first.", "error");
          return;
        }
        state.lastAction = "hashtags";
        runAction(event.currentTarget, function () {
          return window
            .apiFetch("/api/ai/products/" + productId + "/hashtags", { method: "POST" })
            .then(function (data) {
              return [
                {
                  caption: "",
                  hashtags: data.hashtags,
                  call_to_action: "",
                  image_idea: "",
                  provider: "ai",
                  model: ""
                }
              ];
            });
        });
      });

    document.getElementById("studio-retry").addEventListener("click", function () {
      document.getElementById("studio-error").classList.add("hidden");
      if (state.lastRun && typeof state.lastRun.fn === "function") {
        runAction(state.lastRun.btn, state.lastRun.fn);
      }
    });
    document.getElementById("studio-results").addEventListener("click", onResultClick);

    /* Group Engagement (psychology + zero-link shield) mode. */
    var groupState = { caption: "", hashtags: [] };
    var groupBtn = document.getElementById("group-generate-btn");
    if (groupBtn) {
      groupBtn.addEventListener("click", function (event) {
        var niche = document.getElementById("group-niche").value || "car";
        var template = document.getElementById("group-template").value || "show_your_ride";
        var subEl = document.getElementById("group-subculture");
        var trigEl = document.getElementById("group-trigger");
        var subculture = subEl ? subEl.value || "auto" : "auto";
        var trigger = trigEl ? trigEl.value || "auto" : "auto";
        runAction(event.currentTarget, function () {
          return window
            .apiFetch("/api/groups/posts", {
              method: "POST",
              body: JSON.stringify({ niche: niche, template: template, subculture: subculture, trigger: trigger })
            })
            .then(function (content) {
              groupState.caption = content.caption || "";
              groupState.hashtags = content.hashtags || [];
              var box = document.getElementById("group-result");
              box.classList.remove("hidden");
              document.getElementById("studio-empty").classList.add("hidden");
              document.getElementById("group-result-caption").textContent = content.caption || "";
              document.getElementById("group-result-meta").textContent =
                niche + " · " + template + " · " + subculture + " · " + (content.provider || "") + " " + (content.model || "");
              var psych = document.getElementById("group-result-psych");
              if (psych) {
                psych.textContent =
                  "Trigger: " + trigger + " · Zero-link shield passed · Variation spun · Selling only via DM funnel.";
              }
              var tagsWrap = document.getElementById("group-result-tags");
              tagsWrap.innerHTML = "";
              (content.hashtags || []).forEach(function (tag) {
                var chip = document.createElement("span");
                chip.className = "chip";
                chip.textContent = tag;
                tagsWrap.appendChild(chip);
              });
              document.getElementById("group-result-cta").textContent = content.call_to_action
                ? "Comment prompt: " + content.call_to_action
                : "";
              box.scrollIntoView({ behavior: "smooth", block: "nearest" });
              return null;
            });
        });
      });
    }
    var groupCopy = document.getElementById("group-copy-btn");
    if (groupCopy) {
      groupCopy.addEventListener("click", async function () {
        var tags = (groupState.hashtags || []).join(" ");
        var full = groupState.caption + (tags ? "\n\n" + tags : "");
        if (!full.trim()) {
          window.toast("Generate a group post first.", "error");
          return;
        }
        var ok = await window.copyToClipboard(full);
        window.toast(ok ? "Group post text copied — paste it into Facebook." : "Copy failed.", ok ? "success" : "error");
      });
    }
    var groupCopyTags = document.getElementById("group-copy-tags-btn");
    if (groupCopyTags) {
      groupCopyTags.addEventListener("click", async function () {
        var ok = await window.copyToClipboard((groupState.hashtags || []).join(" "));
        window.toast(ok ? "Hashtags copied." : "Copy failed.", ok ? "success" : "error");
      });
    }

    /* Group Post Queue: daily batch + view/edit/copy & mark posted. */
    var batchBtn = document.getElementById("group-batch-btn");
    if (batchBtn) {
      batchBtn.addEventListener("click", function (event) {
        var nicheSel = document.getElementById("group-niche");
        var niche = nicheSel ? nicheSel.value || "car" : "car";
        runAction(event.currentTarget, function () {
          return window
            .apiFetch("/api/groups/queue/generate-batch", {
              method: "POST",
              body: JSON.stringify({ niche: niche, count: 5 })
            })
            .then(function (items) {
              window.toast("Daily batch ready: " + items.length + " posts queued.", "success");
              loadQueue();
              return null;
            });
        });
      });
      loadQueue();
    }
  });
})();
