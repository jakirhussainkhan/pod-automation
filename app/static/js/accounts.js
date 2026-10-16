/* Accounts page: ghost-profile grid, persona modal, health actions. */
(function () {
  "use strict";

  var seq = 0;
  var accountsCache = [];

  var TONE_OPENERS = {
    casual: "Hey",
    enthusiast: "Awesome",
    veteran: "Appreciate it",
    young_gun: "Yo"
  };

  var SAMPLE_M1 = "Hey Mike! Saw your comment in the group — are you looking for one for yourself or as a gift?";

  /**
   * Prefix sample text with the tone opener (mirrors the server rule).
   * @param {string} tone - Persona tone.
   * @returns {string} Preview text.
   */
  function personaPreview(tone) {
    var opener = TONE_OPENERS[tone] || TONE_OPENERS.enthusiast;
    if (SAMPLE_M1.toLowerCase().indexOf(opener.toLowerCase() + ".") === 0 ||
        SAMPLE_M1.toLowerCase().indexOf(opener.toLowerCase() + " ") === 0) {
      return SAMPLE_M1;
    }
    return opener + ". " + SAMPLE_M1;
  }

  /**
   * Usage bar color by saturation.
   * @param {number} used - Used count.
   * @param {number} limit - Limit.
   * @returns {string} Bar classes.
   */
  function barColor(used, limit) {
    var ratio = limit > 0 ? used / limit : 0;
    if (ratio >= 0.9) {
      return "bg-red-500";
    }
    if (ratio >= 0.6) {
      return "bg-amber-500";
    }
    return "bg-green-500";
  }

  /**
   * Health pill for an account.
   * @param {Object} account - Account payload.
   * @returns {HTMLSpanElement} Pill.
   */
  function healthPill(account) {
    var pill = document.createElement("span");
    var status = account.health_status || "healthy";
    var restricted = account.restricted_until && new Date(account.restricted_until) > new Date();
    if (status === "banned") {
      pill.className = "badge badge-red";
      pill.textContent = "Banned";
    } else if (restricted) {
      pill.className = "badge badge-amber";
      pill.textContent = "Restricted until " + window.formatDate(account.restricted_until);
    } else if (status === "warned") {
      pill.className = "badge badge-amber";
      pill.textContent = "Warned";
    } else {
      pill.className = "badge badge-green";
      pill.textContent = "Healthy";
    }
    if (account.health_note) {
      pill.title = account.health_note;
    }
    return pill;
  }

  /**
   * Load and render the accounts grid (request-seq guarded).
   */
  async function loadAccounts() {
    var mySeq = ++seq;
    try {
      var data = await window.apiFetch("/api/accounts?include_inactive=true");
      if (mySeq !== seq) {
        return;
      }
      accountsCache = data.items || [];
      renderGrid();
    } catch (err) {
      window.toast("Could not load accounts: " + err.message, "error");
    }
  }

  /**
   * Render account cards + summary + empty state.
   */
  function renderGrid() {
    var grid = document.getElementById("accounts-grid");
    var empty = document.getElementById("accounts-empty");
    var summary = document.getElementById("accounts-summary");
    grid.innerHTML = "";
    var active = accountsCache.filter(function (a) {
      return a.is_active;
    }).length;
    summary.textContent = accountsCache.length + " account(s), " + active + " active";
    empty.classList.toggle("hidden", accountsCache.length > 0);
    accountsCache.forEach(function (account) {
      grid.appendChild(accountCard(account));
    });
  }

  /**
   * Build one account card.
   * @param {Object} account - Account payload.
   * @returns {HTMLElement} Card.
   */
  function accountCard(account) {
    var card = document.createElement("article");
    card.className = "bg-white/70 dark:bg-slate-900/60 backdrop-blur-md border border-gray-200/60 dark:border-slate-700/50 rounded-xl shadow-lg p-4";
    card.id = "account-" + account.id;
    var head = document.createElement("div");
    head.className = "flex items-center gap-3 mb-2";
    var avatar = document.createElement("div");
    avatar.className = "w-10 h-10 rounded-full bg-gray-800 dark:bg-slate-200 text-white dark:text-slate-900 flex items-center justify-center font-bold flex-shrink-0";
    var label = account.persona_name || account.name || "?";
    avatar.textContent = label.trim().charAt(0).toUpperCase();
    avatar.title = label;
    var titleWrap = document.createElement("div");
    titleWrap.className = "min-w-0";
    var title = document.createElement("p");
    title.className = "font-semibold text-gray-900 dark:text-slate-100 truncate";
    title.textContent = label;
    var handle = document.createElement("p");
    handle.className = "text-xs text-gray-500 dark:text-slate-400 truncate";
    handle.textContent = (account.handle ? "@" + account.handle : account.name) +
      " · prio " + account.priority;
    titleWrap.appendChild(title);
    titleWrap.appendChild(handle);
    head.appendChild(avatar);
    head.appendChild(titleWrap);
    card.appendChild(head);
    var badges = document.createElement("div");
    badges.className = "flex flex-wrap gap-1 mb-2";
    badges.appendChild(healthPill(account));
    if (account.niche_focus) {
      var niche = document.createElement("span");
      niche.className = "badge badge-blue";
      niche.textContent = account.niche_focus;
      badges.appendChild(niche);
    }
    if (account.persona_tone) {
      var tone = document.createElement("span");
      tone.className = "badge badge-gray";
      tone.textContent = account.persona_tone;
      badges.appendChild(tone);
    }
    if (!account.is_active) {
      var paused = document.createElement("span");
      paused.className = "badge badge-gray";
      paused.textContent = "Paused";
      badges.appendChild(paused);
    }
    card.appendChild(badges);
    [["Hourly", account.hourly_used, account.hourly_limit],
     ["Daily", account.daily_used, account.daily_limit]].forEach(function (bar) {
      var row = document.createElement("div");
      row.className = "mb-1";
      var meta = document.createElement("div");
      meta.className = "flex justify-between text-xs text-gray-500 dark:text-slate-400";
      var name = document.createElement("span");
      name.textContent = bar[0];
      var value = document.createElement("span");
      value.textContent = bar[1] + "/" + bar[2];
      meta.appendChild(name);
      meta.appendChild(value);
      var track = document.createElement("div");
      track.className = "stat-bar";
      var fill = document.createElement("div");
      fill.className = "stat-bar-fill " + barColor(bar[1], bar[2]);
      fill.style.width = Math.min(100, Math.round((bar[1] / Math.max(1, bar[2])) * 100)) + "%";
      track.appendChild(fill);
      row.appendChild(meta);
      row.appendChild(track);
      card.appendChild(row);
    });
    var footer = document.createElement("p");
    footer.className = "text-xs text-gray-500 dark:text-slate-400 mt-2";
    footer.textContent = "30d: " + (account.d30_leads || 0) + " DMs · " +
      (account.d30_converted || 0) + " conv · $" +
      Number(account.d30_revenue || 0).toFixed(2) + " · " +
      (Number(account.d30_rate || 0) * 100).toFixed(1) + "%";
    card.appendChild(footer);
    var actions = document.createElement("div");
    actions.className = "flex flex-wrap gap-1 mt-3";
    function addBtn(label, handler, primary) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm " + (primary ? "btn-primary" : "btn-secondary");
      btn.textContent = label;
      btn.addEventListener("click", function () {
        handler(account);
      });
      actions.appendChild(btn);
      return btn;
    }
    addBtn("Edit", openAccountModal, true);
    if (account.health_status === "banned") {
      addBtn("Restore", restoreAccount);
    } else {
      addBtn("Warning", warnAccount);
      addBtn("Ban", banAccount);
    }
    addBtn("Block Group", blockGroupAccount);
    // Delete lives behind the same danger pattern as products (modal footer);
    // here it sits inline but hidden when this is the last active account.
    var actives = accountsCache.filter(function (a) {
      return a.is_active;
    }).length;
    if (!(account.is_active && actives <= 1)) {
      addBtn("Delete", deleteAccount);
    }
    card.appendChild(actions);
    return card;
  }

  /**
   * Open the Add/Edit modal with live persona preview.
   * @param {Object|null} account - Existing account or null for create.
   */
  function openAccountModal(account) {
    var isNew = !account;
    var source = account || {};
    document.getElementById("generic-modal-title").textContent =
      isNew ? "Add Account" : "Edit Account — " + (source.persona_name || source.name);
    var body = document.getElementById("generic-modal-body");
    body.innerHTML = "";
    var grid = document.createElement("div");
    grid.className = "grid grid-cols-1 sm:grid-cols-2 gap-3";
    var inputs = {};
    function field(key, label, type, options) {
      var wrap = document.createElement("div");
      var lab = document.createElement("label");
      lab.className = "field-label";
      lab.textContent = label + (key === "name" ? " *" : "");
      var input;
      if (type === "select") {
        input = document.createElement("select");
        input.className = "field-input";
        (options || []).forEach(function (opt) {
          var el = document.createElement("option");
          el.value = opt.value;
          el.textContent = opt.label;
          input.appendChild(el);
        });
        input.value = source[key] || "";
      } else if (type === "textarea") {
        input = document.createElement("textarea");
        input.className = "field-input";
        input.rows = 2;
        input.value = source[key] || "";
      } else {
        input = document.createElement("input");
        input.type = type || "text";
        if (type === "number") {
          input.min = "1";
        }
        input.className = "field-input";
        input.value = source[key] === null || source[key] === undefined ? "" : String(source[key]);
      }
      inputs[key] = input;
      input.id = "acct-field-" + key;
      lab.setAttribute("for", input.id);
      wrap.appendChild(lab);
      wrap.appendChild(input);
      grid.appendChild(wrap);
      return input;
    }
    field("name", "Account name", "text");
    field("handle", "Handle (without @)", "text");
    field("persona_name", "Persona name", "text");
    var toneInput = field("persona_tone", "Persona tone", "select", [
      { value: "", label: "—" },
      { value: "casual", label: "casual" },
      { value: "enthusiast", label: "enthusiast" },
      { value: "veteran", label: "veteran" },
      { value: "young_gun", label: "young_gun" }
    ]);
    field("persona_bio", "Persona bio", "textarea");
    field("persona_avatar_url", "Avatar URL", "text");
    field("niche_focus", "Niche focus", "select", [
      { value: "", label: "—" },
      { value: "mustang", label: "mustang" },
      { value: "harley", label: "harley" },
      { value: "jdm", label: "jdm" },
      { value: "muscle", label: "muscle" },
      { value: "mixed", label: "mixed" }
    ]);
    field("daily_limit", "Daily limit", "number");
    field("hourly_limit", "Hourly limit", "number");
    field("priority", "Priority (lower = preferred)", "number");
    field("notes", "Notes", "textarea");
    body.appendChild(grid);
    var previewLabel = document.createElement("p");
    previewLabel.className = "field-label mt-4";
    previewLabel.textContent = "M1 preview with this persona";
    var preview = document.createElement("p");
    preview.className = "code-block text-gray-800 dark:text-slate-100";
    function refreshPreview() {
      preview.textContent = personaPreview(toneInput.value || "enthusiast");
    }
    toneInput.addEventListener("change", refreshPreview);
    refreshPreview();
    body.appendChild(previewLabel);
    body.appendChild(preview);
    var footer = document.createElement("div");
    footer.className = "flex justify-end gap-2 mt-4";
    if (!isNew) {
      var actives = accountsCache.filter(function (a) {
        return a.is_active;
      }).length;
      if (!(source.is_active && actives <= 1)) {
        var delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn btn-danger mr-auto";
        delBtn.textContent = "Delete Account";
        delBtn.addEventListener("click", function () {
          window.closeModal("generic-modal");
          deleteAccount(source);
        });
        footer.appendChild(delBtn);
      }
    }
    var save = document.createElement("button");
    save.type = "button";
    save.className = "btn btn-primary";
    save.textContent = isNew ? "Add Account" : "Save Changes";
    save.addEventListener("click", async function () {
      var payload = {};
      Object.keys(inputs).forEach(function (key) {
        var raw = inputs[key].value;
        if (typeof raw === "string") {
          raw = raw.trim();
        }
        if (raw === "" || raw === null || raw === undefined) {
          return;
        }
        if (["daily_limit", "hourly_limit", "priority"].indexOf(key) !== -1) {
          payload[key] = Number(raw);
        } else {
          payload[key] = raw;
        }
      });
      if (isNew && !payload.name) {
        window.toast("Account name is required.", "error");
        return;
      }
      window.setButtonLoading(save, true, "Saving…");
      try {
        if (isNew) {
          await window.apiFetch("/api/accounts", { method: "POST", body: JSON.stringify(payload) });
          window.toast("Account added.", "success");
        } else {
          await window.apiFetch("/api/accounts/" + source.id, { method: "PATCH", body: JSON.stringify(payload) });
          window.toast("Account updated.", "success");
        }
        window.closeModal("generic-modal");
        loadAccounts();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(save, false);
      }
    });
    footer.appendChild(save);
    body.appendChild(footer);
    window.openModal("generic-modal");
  }

  /**
   * Prompt for a free-text note (warning/ban), null on cancel.
   * @param {string} what - Action label.
   * @returns {string|null} Note text.
   */
  function promptNote(what) {
    try {
      var note = window.prompt(what + " note (e.g. FB warned link in post):");
      if (note === null) {
        return null;
      }
      note = note.trim();
      return note || "no detail given";
    } catch (err) {
      return null;
    }
  }

  /**
   * Record a warning against an account.
   * @param {Object} account - Account payload.
   */
  async function warnAccount(account) {
    var note = promptNote("Warning");
    if (note === null) {
      return;
    }
    try {
      await window.apiFetch("/api/accounts/" + account.id + "/warning", {
        method: "POST",
        body: JSON.stringify({ note: note })
      });
      window.toast("Warning logged — account auto-paused.", "success");
      loadAccounts();
    } catch (err) {
      window.toast(err.message, "error");
    }
  }

  /**
   * Record a ban against an account.
   * @param {Object} account - Account payload.
   */
  async function banAccount(account) {
    var confirmed = await window.confirmDialog(
      "Mark " + (account.persona_name || account.name) + " as banned? DMs pause for the recovery period.",
      { confirmText: "Mark Banned", danger: true }
    );
    if (!confirmed) {
      return;
    }
    var note = promptNote("Ban");
    if (note === null) {
      return;
    }
    try {
      await window.apiFetch("/api/accounts/" + account.id + "/ban", {
        method: "POST",
        body: JSON.stringify({ note: note })
      });
      window.toast("Account marked as banned.", "success");
      loadAccounts();
    } catch (err) {
      window.toast(err.message, "error");
    }
  }

  /**
   * Restore an account to healthy.
   * @param {Object} account - Account payload.
   */
  async function restoreAccount(account) {
    try {
      await window.apiFetch("/api/accounts/" + account.id + "/restore", { method: "POST" });
      window.toast("Account restored to healthy.", "success");
      loadAccounts();
    } catch (err) {
      window.toast(err.message, "error");
    }
  }

  /**
   * Manually block an account from a group.
   * @param {Object} account - Account payload.
   */
  async function blockGroupAccount(account) {
    var group = null;
    try {
      group = window.prompt("Block " + (account.persona_name || account.name) + " from which group?");
    } catch (err) {
      group = null;
    }
    if (!group || !group.trim()) {
      return;
    }
    try {
      await window.apiFetch("/api/accounts/" + account.id + "/block-group", {
        method: "POST",
        body: JSON.stringify({ group_name: group.trim(), reason: "manual" })
      });
      window.toast("Account blocked from " + group.trim() + ".", "success");
      loadAccounts();
    } catch (err) {
      window.toast(err.message, "error");
    }
  }

  /**
   * Delete an account (leads detach, last active is refused server-side).
   * @param {Object} account - Account payload.
   */
  async function deleteAccount(account) {
    var confirmed = await window.confirmDialog(
      "Delete account " + (account.persona_name || account.name) + "? Assigned leads become unassigned.",
      { confirmText: "Delete", danger: true }
    );
    if (!confirmed) {
      return;
    }
    try {
      await window.apiFetch("/api/accounts/" + account.id, {
        method: "DELETE",
        headers: { "X-Confirm-Delete": "true" }
      });
      window.toast("Account deleted.", "success");
      loadAccounts();
    } catch (err) {
      window.toast(err.message, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("accounts-add-btn").addEventListener("click", function () {
      openAccountModal(null);
    });
    document.getElementById("accounts-empty-add").addEventListener("click", function () {
      openAccountModal(null);
    });
    document.getElementById("accounts-refresh-btn").addEventListener("click", loadAccounts);
    // Deep link from the dashboard overview card (#<account id>).
    try {
      var hash = window.location.hash.replace("#", "");
      if (hash && /^\d+$/.test(hash)) {
        setTimeout(function () {
          var card = document.getElementById("account-" + hash);
          if (card && card.scrollIntoView) {
            card.scrollIntoView({ block: "center" });
            card.classList.add("ring-2", "ring-gray-500");
          }
        }, 600);
      }
    } catch (err) {
      /* Deep link is best-effort. */
    }
    loadAccounts();
  });
})();
