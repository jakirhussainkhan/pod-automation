/* Shared helpers for the POD Automation Dashboard (plain script, ES2020). */
(function () {
  "use strict";

  var THEME_KEY = "pod-automation-theme";

  /**
   * Get the stored theme preference ("light" | "dark" | "system").
   * @returns {string} Stored preference, defaults to "system".
   */
  function getStoredTheme() {
    try {
      var value = localStorage.getItem(THEME_KEY);
      if (value === "light" || value === "dark" || value === "system") {
        return value;
      }
    } catch (err) {
      /* localStorage unavailable (private mode): fall through. */
    }
    return "system";
  }

  /**
   * Check whether the OS prefers dark mode.
   * @returns {boolean} True when the system prefers dark.
   */
  function systemPrefersDark() {
    return (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    );
  }

  /**
   * Resolve the effective theme for a preference.
   * @param {string} preference - "light" | "dark" | "system".
   * @returns {string} "light" or "dark".
   */
  function resolveTheme(preference) {
    if (preference === "light" || preference === "dark") {
      return preference;
    }
    return systemPrefersDark() ? "dark" : "light";
  }

  /**
   * Update the topbar toggle icons for the effective theme.
   * @param {string} effective - "light" or "dark".
   */
  function syncThemeIcons(effective) {
    var sun = document.getElementById("theme-icon-sun");
    var moon = document.getElementById("theme-icon-moon");
    var toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.setAttribute(
        "aria-label",
        effective === "dark" ? "Switch to light mode" : "Switch to dark mode"
      );
      toggle.setAttribute(
        "title",
        effective === "dark" ? "Switch to light mode" : "Switch to dark mode"
      );
    }
    if (sun) {
      sun.classList.toggle("hidden", effective !== "dark");
    }
    if (moon) {
      moon.classList.toggle("hidden", effective === "dark");
    }
  }

  /**
   * Apply a theme preference to <html> and persist it.
   * @param {string} preference - "light" | "dark" | "system".
   */
  function setTheme(preference) {
    var value = preference === "dark" || preference === "light" ? preference : "system";
    try {
      localStorage.setItem(THEME_KEY, value);
    } catch (err) {
      /* Ignore persistence failures; still apply for this session. */
    }
    var effective = resolveTheme(value);
    document.documentElement.classList.toggle("dark", effective === "dark");
    try {
      document.documentElement.style.colorScheme = effective;
    } catch (err) {
      /* Older browsers: ignore. */
    }
    syncThemeIcons(effective);
    document.dispatchEvent(
      new CustomEvent("pod-theme-change", { detail: { preference: value, effective: effective } })
    );
  }

  /**
   * Wire the topbar toggle + OS theme changes.
   */
  function initTheme() {
    var initial = getStoredTheme();
    var effective = resolveTheme(initial);
    document.documentElement.classList.toggle("dark", effective === "dark");
    syncThemeIcons(effective);
    var toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var current = resolveTheme(getStoredTheme());
        setTheme(current === "dark" ? "light" : "dark");
      });
    }
    if (typeof window.matchMedia === "function") {
      var media = window.matchMedia("(prefers-color-scheme: dark)");
      function onSystemChange() {
        if (getStoredTheme() === "system") {
          var next = resolveTheme("system");
          document.documentElement.classList.toggle("dark", next === "dark");
          syncThemeIcons(next);
          document.dispatchEvent(
            new CustomEvent("pod-theme-change", {
              detail: { preference: "system", effective: next }
            })
          );
        }
      }
      if (typeof media.addEventListener === "function") {
        media.addEventListener("change", onSystemChange);
      } else if (typeof media.addListener === "function") {
        media.addListener(onSystemChange);
      }
    }
  }

  /**
   * Fetch JSON with readable errors.
   * @param {string} url - Request URL.
   * @param {RequestInit} [options] - Optional fetch options.
   * @returns {Promise<any>} Parsed JSON body (null for 204).
   */
  async function apiFetch(url, options) {
    var mergedOptions = Object.assign({}, options || {}, {
      headers: Object.assign(
        { "Content-Type": "application/json" },
        (options && options.headers) || {}
      )
    });
    var response = await fetch(url, mergedOptions);
    if (response.status === 204) {
      return null;
    }
    var payload = null;
    try {
      payload = await response.json();
    } catch (parseError) {
      var netError = new Error(
        "Request to " + url + " failed with status " + response.status + " and non-JSON body."
      );
      netError.status = response.status;
      throw netError;
    }
    if (!response.ok) {
      var detail =
        (payload && (payload.detail || payload.message || payload.error)) ||
        ("Request to " + url + " failed with status " + response.status + ".");
      var message = Array.isArray(detail)
        ? detail
            .map(function (item) {
              if (item && typeof item === "object" && item.msg) {
                var loc = Array.isArray(item.loc) ? item.loc.join(".") + ": " : "";
                return loc + item.msg;
              }
              return JSON.stringify(item);
            })
            .join("; ")
        : detail;
      var err = new Error(typeof message === "string" ? message : JSON.stringify(message));
      err.status = response.status;
      throw err;
    }
    return payload;
  }

  /**
   * Escape text for safe HTML insertion.
   * @param {unknown} value - Value to escape.
   * @returns {string} Escaped string.
   */
  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;")
      .replace(/`/g, "&#96;");
  }

  /**
   * Debounce a function call.
   * @param {Function} fn - Function to debounce.
   * @param {number} wait - Delay in milliseconds.
   * @returns {Function} Debounced function.
   */
  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var self = this;
      if (timer) {
        clearTimeout(timer);
      }
      timer = setTimeout(function () {
        timer = null;
        fn.apply(self, args);
      }, wait);
    };
  }

  /**
   * Format an ISO UTC timestamp in the user's local time.
   * @param {string|null} iso - ISO timestamp.
   * @returns {string} Localized date-time or an em dash.
   */
  function formatDate(iso) {
    if (!iso) {
      return "\u2014";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "\u2014";
    }
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short"
    }).format(date);
  }

  /**
   * Describe how long ago an ISO timestamp was.
   * @param {string|null} iso - ISO timestamp.
   * @returns {string} Relative time label.
   */
  function timeAgo(iso) {
    if (!iso) {
      return "never";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "unknown time";
    }
    var seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 0) {
      return "in the future";
    }
    if (seconds < 60) {
      return "just now";
    }
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
      return minutes + (minutes === 1 ? " minute ago" : " minutes ago");
    }
    var hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return hours + (hours === 1 ? " hour ago" : " hours ago");
    }
    var days = Math.floor(hours / 24);
    if (days < 30) {
      return days + (days === 1 ? " day ago" : " days ago");
    }
    return formatDate(iso);
  }

  /**
   * Describe how far in the future an ISO timestamp is.
   * @param {string|null} iso - ISO timestamp.
   * @returns {string} Relative future label.
   */
  function relativeFuture(iso) {
    if (!iso) {
      return "unscheduled";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "unknown time";
    }
    var seconds = Math.floor((date.getTime() - Date.now()) / 1000);
    if (seconds <= 0) {
      return "due now";
    }
    if (seconds < 60) {
      return "in under a minute";
    }
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
      return "in " + minutes + (minutes === 1 ? " minute" : " minutes");
    }
    var hours = Math.floor(minutes / 60);
    if (hours < 48) {
      return "in " + hours + (hours === 1 ? " hour" : " hours");
    }
    var days = Math.floor(hours / 24);
    if (days < 30) {
      return "in " + days + (days === 1 ? " day" : " days");
    }
    return formatDate(iso);
  }

  /**
   * Truncate text with an ellipsis.
   * @param {string} text - Source text.
   * @param {number} maxLength - Maximum length.
   * @returns {string} Truncated text.
   */
  function truncate(text, maxLength) {
    var value = String(text === null || text === undefined ? "" : text);
    if (value.length <= maxLength) {
      return value;
    }
    return value.slice(0, maxLength).trimEnd() + "\u2026";
  }

  /**
   * Show a toast notification that auto-dismisses after 4 seconds.
   * @param {string} message - Message text.
   * @param {string} [type] - One of success, error, info.
   */
  function toast(message, type) {
    var container = document.getElementById("toast-container");
    if (!container) {
      return;
    }
    var kind = type === "error" ? "error" : type === "info" ? "info" : "success";
    var node = document.createElement("div");
    node.className = "toast toast-" + kind;
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    var text = document.createElement("span");
    text.textContent = message;
    var close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Dismiss notification");
    close.textContent = "\u00d7";
    close.addEventListener("click", function () {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
    });
    node.appendChild(text);
    node.appendChild(close);
    container.appendChild(node);
    setTimeout(function () {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
    }, 4000);
  }

  var modalTriggers = {};

  /**
   * Remove demo rows (is_demo) after confirmation; full wipe needs WIPE ALL DATA.
   * Used by the Products page and Settings danger zone for a clean start.
   * Safe mode only purges seeded demo rows and leaves real records intact.
   * @param {HTMLButtonElement} btn - Trigger button for loading state.
   * @param {Function} [onDone] - Called after a successful wipe.
   */
  async function clearDummyData(btn, onDone) {
    var confirmed = await confirmDialog(
      "Remove demo data only? Real leads, posts, and revenue records are kept.",
      { confirmText: "Clear Demo Data", danger: true }
    );
    if (!confirmed) {
      return;
    }
    // Offer an explicit full-wipe path guarded by typed confirmation.
    var wipeAll = await confirmDialog(
      "Wipe EVERYTHING including your real data? Type WIPE ALL DATA on the next prompt to proceed, or Cancel to keep real data.",
      { confirmText: "Wipe Everything", danger: true }
    );
    var body = { wipe_all: false };
    if (wipeAll) {
      var typed = await promptDialog(
        "Type WIPE ALL DATA to permanently wipe ALL data (products, posts, leads, queue). This cannot be undone.",
        "WIPE ALL DATA",
        { confirmText: "Wipe Everything" }
      );
      if (typed === "WIPE ALL DATA") {
        body = { wipe_all: true, confirmation: "WIPE ALL DATA" };
      } else {
        if (typed !== null) {
          toast('Full wipe cancelled: you must type exactly "WIPE ALL DATA".', "info");
        }
        return;
      }
    }
    setButtonLoading(btn, true, "Clearing…");
    try {
      var result = await apiFetch("/api/settings/clear-dummy-data", {
        method: "POST",
        headers: { "X-Confirm-Delete": "true" },
        body: JSON.stringify(body)
      });
      toast(
        "Clean slate: " + result.products + " products, " + result.posts + " posts, " +
          result.leads + " leads, " + result.queued_posts + " queued removed.",
        "success"
      );
      if (typeof onDone === "function") {
        onDone(result);
      }
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setButtonLoading(btn, false);
    }
  }

  /**
   * Open a modal, focusing its first focusable element.
   * @param {string} id - Modal backdrop element id.
   */
  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) {
      return;
    }
    modalTriggers[id] = document.activeElement;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    var focusable = modal.querySelector(
      "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"
    );
    if (focusable) {
      focusable.focus();
    }
  }

  /**
   * Close a modal and restore focus to its trigger.
   * @param {string} id - Modal backdrop element id.
   */
  function closeModal(id) {
    var modal = document.getElementById(id);
    if (!modal) {
      return;
    }
    modal.hidden = true;
    if (!document.querySelector(".modal-backdrop:not([hidden])")) {
      document.body.style.overflow = "";
    }
    var trigger = modalTriggers[id];
    if (trigger && typeof trigger.focus === "function") {
      trigger.focus();
    }
    delete modalTriggers[id];
    // If the confirm dialog is dismissed via Escape/backdrop, resolve the
    // pending promise with false so `await confirmDialog()` never hangs.
    if (id === "confirm-modal") {
      cancelConfirm();
    }
    if (id === "prompt-modal") {
      cancelPrompt();
    }
  }

  // Escape closes the topmost open modal; backdrop clicks close their modal.
  document.addEventListener("keydown", function (event) {
    var open = Array.prototype.slice.call(
      document.querySelectorAll(".modal-backdrop:not([hidden])")
    );
    // Trap Tab focus inside the topmost open modal.
    if (event.key === "Tab" && open.length > 0) {
      var modal = open[open.length - 1];
      var focusables = Array.prototype.slice
        .call(
          modal.querySelectorAll(
            "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"
          )
        )
        .filter(function (el) {
          return !el.disabled && el.offsetParent !== null;
        });
      if (focusables.length === 0) {
        return;
      }
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (!modal.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (event.key !== "Escape") {
      return;
    }
    if (open.length > 0) {
      closeModal(open[open.length - 1].id);
    }
  });
  document.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.classList && target.classList.contains("modal-backdrop")) {
      closeModal(target.id);
    }
  });

  var confirmState = { resolve: null };

  /**
   * Resolve any in-flight confirm with `false`. Called when the confirm modal
   * is dismissed (Escape, backdrop click, or a superseding confirm call).
   */
  function cancelConfirm() {
    if (confirmState && confirmState.resolve) {
      var pending = confirmState.resolve;
      confirmState.resolve = null;
      pending(false);
    }
  }

  /**
   * Show the shared confirm dialog.
   * @param {string} message - Confirmation message.
   * @param {Object} [options] - Labels and danger flag.
   * @returns {Promise<boolean>} True when confirmed.
   */
  function confirmDialog(message, options) {
    var opts = options || {};
    var modal = document.getElementById("confirm-modal");
    var text = document.getElementById("confirm-modal-message");
    var okBtn = document.getElementById("confirm-modal-ok");
    var cancelBtn = document.getElementById("confirm-modal-cancel");
    if (!modal || !text || !okBtn || !cancelBtn) {
      return Promise.resolve(window.confirm(message));
    }
    text.textContent = message;
    okBtn.textContent = opts.confirmText || "Confirm";
    okBtn.className = "btn " + (opts.danger ? "btn-danger" : "btn-primary");
    // Supersede any previous confirm (resolves it false before we take over).
    cancelConfirm();
    return new Promise(function (resolve) {
      confirmState.resolve = resolve;
      function done(value) {
        // Clear handlers + state first so the closeModal() below can't
        // re-enter cancelConfirm() and resolve a second time.
        okBtn.onclick = null;
        cancelBtn.onclick = null;
        confirmState.resolve = null;
        closeModal("confirm-modal");
        resolve(value);
      }
      // Direct onclick assignment (not addEventListener) so an Escape-dismissed
      // dialog can't leak listeners that later double-fire.
      okBtn.onclick = function () {
        done(true);
      };
      cancelBtn.onclick = function () {
        done(false);
      };
      openModal("confirm-modal");
    });
  }

  var promptState = { resolve: null };

  /**
   * Resolve any in-flight prompt with null (dismissed).
   */
  function cancelPrompt() {
    if (promptState && promptState.resolve) {
      var pending = promptState.resolve;
      promptState.resolve = null;
      pending(null);
    }
  }

  /**
   * Show a modal that requires the user to type an exact confirmation string.
   * Falls back to the native prompt when the modal markup is unavailable.
   * @param {string} message - Explanatory message.
   * @param {string} expected - Exact text the user must type.
   * @param {Object} [options] - Confirm button label.
   * @returns {Promise<string|null>} Typed value, or null when dismissed.
   */
  function promptDialog(message, expected, options) {
    var opts = options || {};
    var modal = document.getElementById("prompt-modal");
    var text = document.getElementById("prompt-modal-message");
    var input = document.getElementById("prompt-modal-input");
    var hint = document.getElementById("prompt-modal-hint");
    var okBtn = document.getElementById("prompt-modal-ok");
    var cancelBtn = document.getElementById("prompt-modal-cancel");
    if (!modal || !text || !input || !okBtn || !cancelBtn) {
      var fallback = null;
      try {
        fallback = window.prompt(message);
      } catch (err) {
        fallback = null;
      }
      return Promise.resolve(fallback);
    }
    text.textContent = message;
    input.value = "";
    input.placeholder = expected;
    hint.textContent =
      'Type "' + expected + '" and click ' + (opts.confirmText || "Confirm") + ", or Cancel.";
    okBtn.textContent = opts.confirmText || "Confirm";
    cancelPrompt();
    return new Promise(function (resolve) {
      promptState.resolve = resolve;
      function done(value) {
        okBtn.onclick = null;
        cancelBtn.onclick = null;
        input.onkeydown = null;
        promptState.resolve = null;
        closeModal("prompt-modal");
        resolve(value);
      }
      okBtn.onclick = function () {
        done(input.value);
      };
      cancelBtn.onclick = function () {
        done(null);
      };
      input.onkeydown = function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          done(input.value);
        }
      };
      openModal("prompt-modal");
    });
  }

  /**
   * Disable a button with a spinner while loading, then restore it.
   * @param {HTMLButtonElement} btn - Button element.
   * @param {boolean} isLoading - Loading state to apply.
   * @param {string} [loadingText] - Text shown while loading.
   */
  function setButtonLoading(btn, isLoading, loadingText) {
    if (!btn) {
      return;
    }
    if (isLoading) {
      if (btn.dataset.originalHtml === undefined) {
        btn.dataset.originalHtml = btn.innerHTML;
      }
      btn.disabled = true;
      btn.innerHTML = "";
      var spinner = document.createElement("span");
      spinner.className = "btn-spinner";
      spinner.setAttribute("aria-hidden", "true");
      btn.appendChild(spinner);
      var label = document.createElement("span");
      label.textContent = loadingText || "Working\u2026";
      btn.appendChild(label);
    } else {
      btn.disabled = false;
      if (btn.dataset.originalHtml !== undefined) {
        btn.innerHTML = btn.dataset.originalHtml;
        delete btn.dataset.originalHtml;
      }
    }
  }

  /**
   * Render pagination controls into a container.
   * @param {HTMLElement} container - Target container.
   * @param {Object} page - Object with total, skip and limit.
   * @param {Function} onPageChange - Called with the new skip value.
   */
  function renderPagination(container, page, onPageChange) {
    if (!container) {
      return;
    }
    container.innerHTML = "";
    var total = page.total || 0;
    var limit = page.limit || 10;
    var skip = page.skip || 0;
    var pages = Math.max(1, Math.ceil(total / limit));
    var current = Math.floor(skip / limit) + 1;
    var info = document.createElement("span");
    info.className = "text-sm text-gray-600 dark:text-slate-300";
    var from = total === 0 ? 0 : skip + 1;
    var to = Math.min(skip + limit, total);
    info.textContent = "Showing " + from + "\u2013" + to + " of " + total;
    container.appendChild(info);
    if (pages <= 1) {
      return;
    }
    var nav = document.createElement("div");
    nav.className = "flex items-center gap-1";
    nav.setAttribute("role", "navigation");
    nav.setAttribute("aria-label", "Pagination");
    function addButton(label, targetPage, disabled, ariaLabel) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-secondary btn-sm";
      btn.textContent = label;
      btn.disabled = !!disabled;
      if (ariaLabel) {
        btn.setAttribute("aria-label", ariaLabel);
      }
      if (!disabled) {
        btn.addEventListener("click", function () {
          onPageChange((targetPage - 1) * limit);
        });
      }
      nav.appendChild(btn);
    }
    addButton("\u00ab Prev", current - 1, current <= 1, "Previous page");
    var start = Math.max(1, Math.min(current - 2, pages - 4));
    var end = Math.min(pages, start + 4);
    start = Math.max(1, end - 4);
    for (var p = start; p <= end; p++) {
      (function (pageNum) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = String(pageNum);
        btn.className =
          "btn btn-sm " + (pageNum === current ? "btn-primary" : "btn-secondary");
        btn.setAttribute("aria-label", "Page " + pageNum);
        if (pageNum !== current) {
          btn.addEventListener("click", function () {
            onPageChange((pageNum - 1) * limit);
          });
        } else {
          btn.disabled = true;
        }
        nav.appendChild(btn);
      })(p);
    }
    addButton("Next \u00bb", current + 1, current >= pages, "Next page");
    container.appendChild(nav);
  }

  /**
   * Copy text using the clipboard API with a textarea fallback.
   * @param {string} text - Text to copy.
   * @returns {Promise<boolean>} True on success.
   */
  function copyToClipboard(text) {
    var value = String(text === null || text === undefined ? "" : text);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value).then(
        function () {
          return true;
        },
        function () {
          return fallbackCopy(value);
        }
      );
    }
    return Promise.resolve(fallbackCopy(value));
  }

  /**
   * Copy text with a hidden textarea element.
   * @param {string} value - Text to copy.
   * @returns {boolean} True on success.
   */
  function fallbackCopy(value) {
    var area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  var badgeColors = {
    active: "badge-green",
    published: "badge-green",
    draft: "badge-gray",
    archived: "badge-gray",
    scheduled: "badge-blue",
    failed: "badge-red",
    INFO: "badge-blue",
    WARNING: "badge-amber",
    ERROR: "badge-red"
  };

  /**
   * Build safe badge HTML for a status or level value.
   * @param {string} statusValue - Status text.
   * @returns {string} Safe HTML string.
   */
  function statusBadge(statusValue) {
    var key = String(statusValue === null || statusValue === undefined ? "" : statusValue);
    var cls = badgeColors[key] || "badge-gray";
    return '<span class="badge ' + cls + '">' + escapeHtml(key) + "</span>";
  }

  /**
   * Attach an image error fallback that swaps in a placeholder box.
   * @param {HTMLImageElement} img - Image element to guard.
   */
  function guardImage(img) {
    if (!img) {
      return;
    }
    img.addEventListener("error", function handleError() {
      img.removeEventListener("error", handleError);
      var box = document.createElement("div");
      box.className = "thumb-fallback";
      box.textContent = "No image";
      if (img.parentNode) {
        img.parentNode.replaceChild(box, img);
      }
    });
  }

  /**
   * Load the AI status badge in the top bar.
   */
  async function loadAiBadge() {
    var badge = document.getElementById("ai-status-badge");
    if (!badge) {
      return;
    }
    try {
      var data = await apiFetch("/api/ai/status");
      badge.textContent = "";
      var dot = document.createElement("span");
      dot.className = "badge-dot";
      dot.setAttribute("aria-hidden", "true");
      var label = document.createElement("span");
      if (data.mock_mode) {
        badge.className = "badge badge-amber";
        label.textContent = "Mock mode";
      } else if (data.primary_provider === "groq" && data.groq_configured) {
        badge.className = "badge badge-green";
        label.textContent = "Groq ready";
      } else if (data.primary_provider === "openai" && data.openai_configured) {
        badge.className = "badge badge-green";
        label.textContent = "OpenAI ready";
      } else {
        badge.className = "badge badge-red";
        label.textContent = "No AI key";
      }
      badge.appendChild(dot);
      badge.appendChild(label);
    } catch (err) {
      badge.className = "badge badge-red";
      badge.textContent = "AI status unknown";
    }
  }

  /**
   * Reparent every modal backdrop to <body> so fixed positioning is never
   * clipped by an ancestor with backdrop-filter / transform / filter.
   * Page templates may declare modals inside <main>; this moves them out.
   */
  function reparentModalsToBody() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".modal-backdrop"),
      function (modal) {
        if (modal.parentNode !== document.body) {
          document.body.appendChild(modal);
        }
      }
    );
  }

  /**
   * Wire the mobile sidebar toggle and backdrop.
   */
  function initSidebar() {
    var toggle = document.getElementById("sidebar-toggle");
    var backdrop = document.getElementById("sidebar-backdrop");
    var sidebar = document.getElementById("sidebar");
    if (!toggle || !sidebar) {
      return;
    }
    function close() {
      document.body.classList.remove("sidebar-open");
      if (backdrop) {
        backdrop.hidden = true;
      }
      toggle.setAttribute("aria-label", "Open navigation menu");
      toggle.setAttribute("aria-expanded", "false");
    }
    toggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("sidebar-open");
      if (backdrop) {
        backdrop.hidden = !open;
      }
      toggle.setAttribute(
        "aria-label",
        open ? "Close navigation menu" : "Open navigation menu"
      );
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    if (backdrop) {
      backdrop.addEventListener("click", close);
    }
    // Escape closes the mobile sidebar when it is open.
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
        close();
      }
    });
    sidebar.addEventListener("click", function (event) {
      if (event.target && event.target.tagName === "A" && window.innerWidth < 1024) {
        close();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initSidebar();
    reparentModalsToBody();
    loadAiBadge();
    var genericClose = document.getElementById("generic-modal-close");
    if (genericClose) {
      genericClose.addEventListener("click", function () {
        closeModal("generic-modal");
      });
    }
  });

  window.apiFetch = apiFetch;
  window.PODTheme = {
    get: getStoredTheme,
    set: setTheme,
    effective: function () {
      return resolveTheme(getStoredTheme());
    }
  };
  window.setTheme = setTheme;
  window.getTheme = getStoredTheme;
  window.escapeHtml = escapeHtml;
  window.debounce = debounce;
  window.formatDate = formatDate;
  window.timeAgo = timeAgo;
  window.relativeFuture = relativeFuture;
  window.truncate = truncate;
  window.toast = toast;
  window.showToast = toast;
  window.openModal = openModal;
  window.closeModal = closeModal;
  window.confirmDialog = confirmDialog;
  window.promptDialog = promptDialog;
  window.setButtonLoading = setButtonLoading;
  window.renderPagination = renderPagination;
  window.copyToClipboard = copyToClipboard;
  window.clearDummyData = clearDummyData;
  window.statusBadge = statusBadge;
  window.guardImage = guardImage;
})();
