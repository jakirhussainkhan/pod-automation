/* Overview Dashboard: summary, activity, accounts + quick actions. (ES2020, vanilla JS) */
(function () {
  "use strict";

  var REFRESH_MS = 60000;
  var refreshTimer = null;
  var loadSeq = 0;

  /**
   * Format an ISO timestamp as relative time ("5 minutes ago").
   * @param {string|null} iso - ISO timestamp.
   * @returns {string} Relative label.
   */
  function relativeTime(iso) {
    if (!iso) {
      return "never";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "unknown time";
    }
    var diffSec = Math.round((date.getTime() - Date.now()) / 1000);
    var abs = Math.abs(diffSec);
    var rtf;
    try {
      rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    } catch (err) {
      return window.timeAgo ? window.timeAgo(iso) : date.toLocaleString();
    }
    if (abs < 60) {
      return rtf.format(diffSec, "second");
    }
    var minutes = Math.round(diffSec / 60);
    if (Math.abs(minutes) < 60) {
      return rtf.format(minutes, "minute");
    }
    var hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) {
      return rtf.format(hours, "hour");
    }
    var days = Math.round(hours / 24);
    if (Math.abs(days) < 30) {
      return rtf.format(days, "day");
    }
    return window.formatDate ? window.formatDate(iso) : date.toLocaleString();
  }

  /**
   * Show content in the shared generic modal from base.html.
   * @param {string} title - Modal heading.
   * @param {HTMLElement} bodyNode - Body content node.
   */
  function showModal(title, bodyNode) {
    var titleEl = document.getElementById("generic-modal-title");
    var bodyEl = document.getElementById("generic-modal-body");
    if (!titleEl || !bodyEl) {
      return;
    }
    titleEl.textContent = title;
    bodyEl.innerHTML = "";
    bodyEl.appendChild(bodyNode);
    window.openModal("generic-modal");
  }

  /**
   * Build a simple key/value table for modal display.
   * @param {Array} rows - [label, value] pairs.
   * @returns {HTMLElement} Table wrapper.
   */
  function kvTable(rows) {
    var wrap = document.createElement("div");
    wrap.className = "overflow-x-auto";
    var table = document.createElement("table");
    table.className = "w-full text-sm";
    var tbody = document.createElement("tbody");
    rows.forEach(function (pair) {
      var tr = document.createElement("tr");
      tr.className = "border-b border-gray-100 dark:border-slate-800";
      var k = document.createElement("td");
      k.className = "py-2 pr-3 text-gray-500 dark:text-slate-400";
      k.textContent = pair[0];
      var v = document.createElement("td");
      v.className = "py-2 font-medium text-gray-900 dark:text-slate-100";
      v.textContent = String(pair[1]);
      tr.appendChild(k);
      tr.appendChild(v);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  /**
   * Render summary cards from the overview payload.
   * @param {Object} summary - Summary object.
   */
  function renderSummary(summary) {
    var pending = summary.pending_actions || {};
    document.getElementById("stat-total-products").textContent = String(summary.total_products || 0);
    document.getElementById("stat-active-leads").textContent = String(summary.active_leads || 0);
    document.getElementById("stat-messages-today").textContent = String(summary.messages_sent_today || 0);
    document.getElementById("stat-revenue").textContent =
      "$" + Number(summary.conversion_revenue || 0).toFixed(2);
    document.getElementById("stat-pending").textContent = String(pending.total || 0);
    var breakdown = document.getElementById("pending-breakdown");
    breakdown.textContent =
      "Reply " + (pending.reply_check || 0) +
      " · Overdue " + (pending.overdue || 0) +
      " · M2 " + (pending.m2_waiting || 0) +
      " · Cold " + (pending.cold || 0);
  }

  /**
   * Render the recent activity stream.
   * @param {Array} items - Activity entries.
   */
  function renderActivity(items) {
    var list = document.getElementById("activity-stream");
    var empty = document.getElementById("activity-empty");
    if (!list || !empty) {
      return;
    }
    list.innerHTML = "";
    if (!items || items.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    items.forEach(function (entry) {
      var li = document.createElement("li");
      li.className = "py-3 flex items-start gap-3";
      var badge = document.createElement("span");
      badge.innerHTML = window.statusBadge(entry.level || "INFO");
      var body = document.createElement("div");
      body.className = "min-w-0 flex-1";
      var msg = document.createElement("p");
      msg.className = "text-sm text-gray-900 dark:text-slate-100";
      msg.textContent = entry.description || entry.message || entry.event || "Activity";
      var meta = document.createElement("p");
      meta.className = "text-xs text-gray-400 dark:text-slate-500 mt-1";
      meta.textContent = (entry.event || entry.event_type || "event") + " · " + relativeTime(entry.created_at);
      meta.title = entry.created_at || "";
      body.appendChild(msg);
      body.appendChild(meta);
      li.appendChild(badge);
      li.appendChild(body);
      list.appendChild(li);
    });
  }

  /**
   * Render multi-account mini cards with DM rate-limit progress bars.
   * @param {Array} accounts - Account rows from the overview payload.
   */
  function renderAccounts(accounts) {
    var grid = document.getElementById("account-status");
    var empty = document.getElementById("accounts-empty");
    if (!grid || !empty) {
      return;
    }
    grid.innerHTML = "";
    if (!accounts || accounts.length === 0) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    accounts.forEach(function (account) {
      var card = document.createElement("a");
      card.href = "/accounts";
      card.className = "dash-account";
      var head = document.createElement("div");
      head.className = "flex items-center gap-2 min-w-0";
      var name = document.createElement("span");
      name.className = "font-medium text-gray-900 dark:text-slate-100 truncate";
      name.textContent = account.persona_name || account.handle || account.name || ("Account #" + account.id);
      var health = document.createElement("span");
      var status = (account.health_status || "healthy").toLowerCase();
      health.className = "badge " + (status === "healthy" ? "badge-green" : status === "warned" ? "badge-amber" : "badge-red");
      health.textContent = status;
      if (!account.is_active) {
        health.textContent += " · paused";
      }
      head.appendChild(name);
      head.appendChild(health);
      card.appendChild(head);

      var sub = document.createElement("p");
      sub.className = "text-xs text-gray-500 dark:text-slate-400 mt-1";
      var handleBit = account.handle ? "@" + String(account.handle).replace(/^@/, "") + " · " : "";
      sub.textContent = handleBit + "warnings: " + (account.warnings_count || 0);
      card.appendChild(sub);

      var dailyUsed = Number(account.daily_used || account.today_sent || 0);
      var dailyCap = Number(account.daily_limit || account.daily_cap || 20);
      var hourlyUsed = Number(account.hourly_used || 0);
      var hourlyCap = Number(account.hourly_limit || 10);

      [["Daily", dailyUsed, dailyCap], ["Hourly", hourlyUsed, hourlyCap]].forEach(function (bar) {
        var label = document.createElement("div");
        label.className = "flex justify-between text-xs mt-2 text-gray-500 dark:text-slate-400";
        var left = document.createElement("span");
        left.textContent = bar[0];
        var right = document.createElement("span");
        right.textContent = bar[1] + "/" + bar[2];
        label.appendChild(left);
        label.appendChild(right);
        var track = document.createElement("div");
        track.className = "stat-bar mt-1";
        var fill = document.createElement("div");
        var ratio = bar[2] > 0 ? bar[1] / bar[2] : 0;
        fill.className = "stat-bar-fill " + (ratio >= 0.9 ? "bg-red-500" : ratio >= 0.6 ? "bg-amber-500" : "bg-green-500");
        fill.style.width = Math.min(100, Math.round(ratio * 100)) + "%";
        track.appendChild(fill);
        card.appendChild(label);
        card.appendChild(track);
      });
      grid.appendChild(card);
    });
  }

  /**
   * Load the overview aggregate and render all sections.
   */
  async function loadDashboard() {
    var loading = document.getElementById("dashboard-loading");
    var content = document.getElementById("dashboard-content");
    var errorBox = document.getElementById("dashboard-error");
    var errorText = document.getElementById("dashboard-error-text");
    var statusEl = document.getElementById("overview-status");
    var mySeq = ++loadSeq;
    try {
      var data = await window.apiFetch("/api/dashboard/overview");
      if (mySeq !== loadSeq) {
        return;
      }
      renderSummary(data.summary || {});
      renderActivity(data.recent_activity || []);
      renderAccounts(data.accounts || []);
      if (errorBox) {
        errorBox.classList.add("hidden");
      }
      if (loading) {
        loading.classList.add("hidden");
      }
      if (content) {
        content.classList.remove("hidden");
      }
      if (statusEl) {
        statusEl.textContent = "updated " + new Date().toLocaleTimeString();
      }
    } catch (err) {
      if (mySeq !== loadSeq) {
        return;
      }
      if (errorText) {
        errorText.textContent = "Could not load overview: " + err.message;
      }
      if (errorBox) {
        errorBox.classList.remove("hidden");
      }
      if (loading) {
        loading.classList.add("hidden");
      }
      if (statusEl) {
        statusEl.textContent = "update failed";
      }
    }
  }

  /**
   * Quick action: auto-generate 5 daily batch posts.
   * @param {HTMLButtonElement} btn - Clicked button.
   */
  async function onGenerateBatch(btn) {
    window.setButtonLoading(btn, true, "Generating…");
    try {
      var items = await window.apiFetch("/api/groups/queue/generate-batch", {
        method: "POST",
        body: JSON.stringify({ count: 5 })
      });
      window.toast("Generated " + (items ? items.length : 0) + " queued posts.", "success");
      loadDashboard();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Quick action: smart lead capture modal → bulk-parse.
   */
  function onSmartCapture() {
    var wrap = document.createElement("div");
    wrap.className = "space-y-3";
    var hint = document.createElement("p");
    hint.className = "text-sm text-gray-500 dark:text-slate-400";
    hint.textContent = "Paste group comments (one per line: Name: comment). High-intent leads are saved instantly.";
    var groupLabel = document.createElement("label");
    groupLabel.className = "field-label";
    groupLabel.textContent = "Group name (optional)";
    var groupInput = document.createElement("input");
    groupInput.className = "field-input";
    groupInput.placeholder = "e.g. Mustang Fans";
    var textLabel = document.createElement("label");
    textLabel.className = "field-label";
    textLabel.textContent = "Comments";
    var area = document.createElement("textarea");
    area.className = "field-input";
    area.rows = 8;
    area.placeholder = "Alex: where can I buy this?\nSam - love this design!";
    var submit = document.createElement("button");
    submit.type = "button";
    submit.className = "btn btn-primary w-full";
    submit.textContent = "Parse & Save High-Intent";
    submit.addEventListener("click", async function () {
      var text = area.value.trim();
      if (!text) {
        window.toast("Paste at least one comment first.", "error");
        return;
      }
      window.setButtonLoading(submit, true, "Parsing…");
      try {
        var result = await window.apiFetch("/api/groups/leads/bulk-parse", {
          method: "POST",
          body: JSON.stringify({ text: text, group_name: groupInput.value.trim() || null })
        });
        window.toast(
          "Parsed " + result.total_parsed + ": saved " + result.saved_high + " high-intent lead(s).",
          "success"
        );
        window.closeModal("generic-modal");
        loadDashboard();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(submit, false);
      }
    });
    wrap.appendChild(hint);
    wrap.appendChild(groupLabel);
    wrap.appendChild(groupInput);
    wrap.appendChild(textLabel);
    wrap.appendChild(area);
    wrap.appendChild(submit);
    showModal("Smart Lead Capture", wrap);
  }

  /**
   * Quick action: pending DMs modal from the attention endpoint.
   */
  async function onPendingDMs(btn) {
    window.setButtonLoading(btn, true, "Checking…");
    try {
      var data = await window.apiFetch("/api/group-leads/attention");
      var counts = data.counts || {};
      var wrap = document.createElement("div");
      wrap.className = "space-y-3";
      wrap.appendChild(kvTable([
        ["Reply checks", counts.reply_check || 0],
        ["Overdue", counts.overdue || 0],
        ["M2 waiting", counts.m2_waiting || 0],
        ["Cold follow-ups ready", counts.cold_followup_ready || 0],
        ["Unassigned", counts.unassigned || 0]
      ]));
      var link = document.createElement("a");
      link.href = "/groups";
      link.className = "btn btn-secondary w-full";
      link.textContent = "Open DM Funnel";
      wrap.appendChild(link);
      showModal("Pending DMs", wrap);
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Quick action: DM safety status modal.
   */
  async function onDmSafety(btn) {
    window.setButtonLoading(btn, true, "Loading…");
    try {
      var data = await window.apiFetch("/api/dm-safety/status");
      var wrap = document.createElement("div");
      wrap.className = "space-y-4";
      wrap.appendChild(kvTable([
        ["Account", (data.account_name || "") + " (#" + (data.account_id || "?") + ")"],
        ["Hourly", (data.hourly_used || 0) + " / " + (data.hourly_limit || 0)],
        ["Daily", (data.daily_used || 0) + " / " + (data.daily_limit || 0)],
        ["Next hourly reset", data.next_hourly_reset_at || "—"]
      ]));
      var perAccount = data.accounts || [];
      if (perAccount.length > 0) {
        var heading = document.createElement("h4");
        heading.className = "font-semibold text-sm text-gray-900 dark:text-slate-100";
        heading.textContent = "Per-account quota";
        wrap.appendChild(heading);
        var rows = perAccount.map(function (a) {
          return [
            (a.name || ("#" + a.account_id)) + " (" + (a.health_status || "healthy") + ")",
            (a.hourly_used || 0) + "/" + (a.hourly_limit || 0) + " hourly · " +
            (a.daily_used || 0) + "/" + (a.daily_limit || 0) + " daily"
          ];
        });
        wrap.appendChild(kvTable(rows));
      }
      var link = document.createElement("a");
      link.href = "/groups";
      link.className = "btn btn-secondary w-full";
      link.textContent = "Open Groups Safety Panel";
      wrap.appendChild(link);
      showModal("DM Safety Status", wrap);
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var dateEl = document.getElementById("overview-date");
    if (dateEl) {
      dateEl.textContent = new Intl.DateTimeFormat(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric"
      }).format(new Date());
    }
    var refreshBtn = document.getElementById("overview-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", loadDashboard);
    }
    var retryBtn = document.getElementById("dashboard-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", loadDashboard);
    }
    document.querySelectorAll("[data-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var action = btn.getAttribute("data-action");
        if (action === "generate-batch") {
          onGenerateBatch(btn);
        } else if (action === "smart-capture") {
          onSmartCapture();
        } else if (action === "pending-dms") {
          onPendingDMs(btn);
        } else if (action === "dm-safety") {
          onDmSafety(btn);
        }
      });
    });

    loadDashboard();
    if (refreshTimer) {
      clearInterval(refreshTimer);
    }
    refreshTimer = setInterval(function () {
      if (document.visibilityState === "visible") {
        loadDashboard();
      }
    }, REFRESH_MS);
    window.addEventListener("pagehide", function () {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      loadSeq++;
    });
  });
})();
