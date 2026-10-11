/* Settings page: load, edit, validate and save public settings. */
(function () {
  "use strict";

  var FIELDS = [
    "default_tone",
    "brand_voice",
    "post_language",
    "default_hashtags",
    "posting_enabled",
    "posts_per_day",
    "posting_hours",
    "dm_min_gap_seconds",
    "dm_hourly_cap",
    "dm_daily_cap",
    "reply_check_delay_hours",
    "reply_check_second_hours",
    "cold_lead_days",
    "follow_up_enabled",
    "max_follow_ups",
    "stats_auto_compute",
    "digest_week_start",
    "chart_days",
    "backup_enabled",
    "backup_hour_utc",
    "backup_keep_last",
    "log_retention_days"
  ];

  var postingHours = [];

  /**
   * Highlight the active theme button and update the helper text.
   * @param {string} preference - "light" | "dark" | "system".
   * @param {string} effective - Resolved "light" or "dark".
   */
  function syncThemeOptions(preference, effective) {
    var buttons = document.querySelectorAll("#theme-options [data-theme-value]");
    Array.prototype.forEach.call(buttons, function (btn) {
      var active = btn.getAttribute("data-theme-value") === preference;
      btn.classList.toggle("pill-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
    var hint = document.getElementById("theme-current");
    if (hint) {
      if (preference === "system") {
        hint.textContent = "Following system setting (currently " + effective + ").";
      } else {
        hint.textContent =
          "Using " + preference + " mode. Change any time, or use the top-bar icon.";
      }
    }
  }

  /**
   * Wire the Appearance card to the shared theme manager in app.js.
   */
  function initAppearance() {
    var wrap = document.getElementById("theme-options");
    if (!wrap) {
      return;
    }
    function currentPreference() {
      if (window.PODTheme && typeof window.PODTheme.get === "function") {
        return window.PODTheme.get();
      }
      try {
        return localStorage.getItem("pod-automation-theme") || "system";
      } catch (err) {
        return "system";
      }
    }
    function currentEffective() {
      if (window.PODTheme && typeof window.PODTheme.effective === "function") {
        return window.PODTheme.effective();
      }
      return document.documentElement.classList.contains("dark") ? "dark" : "light";
    }
    function applyPreference(value) {
      if (window.PODTheme && typeof window.PODTheme.set === "function") {
        window.PODTheme.set(value);
      } else if (typeof window.setTheme === "function") {
        window.setTheme(value);
      }
      syncThemeOptions(value, currentEffective());
      window.toast("Theme set to " + value + ".", "success");
    }
    Array.prototype.forEach.call(
      wrap.querySelectorAll("[data-theme-value]"),
      function (btn) {
        btn.addEventListener("click", function () {
          applyPreference(btn.getAttribute("data-theme-value"));
        });
      }
    );
    syncThemeOptions(currentPreference(), currentEffective());
    document.addEventListener("pod-theme-change", function (event) {
      var detail = (event && event.detail) || {};
      syncThemeOptions(
        detail.preference || currentPreference(),
        detail.effective || currentEffective()
      );
    });
  }

  /**
   * Map a setting key to its input element id.
   * @param {string} key - Setting key.
   * @returns {string} Element id.
   */
  function fieldId(key) {
    if (key === "dm_min_gap_seconds") {
      return "setting-dm-min-gap-seconds";
    }
    if (key === "dm_hourly_cap") {
      return "setting-dm-hourly-cap";
    }
    if (key === "dm_daily_cap") {
      return "setting-dm-daily-cap";
    }
    if (key === "reply_check_delay_hours") {
      return "setting-reply-check-delay-hours";
    }
    if (key === "reply_check_second_hours") {
      return "setting-reply-check-second-hours";
    }
    if (key === "cold_lead_days") {
      return "setting-cold-lead-days";
    }
    if (key === "follow_up_enabled") {
      return "setting-follow-up-enabled";
    }
    if (key === "max_follow_ups") {
      return "setting-max-follow-ups";
    }
    if (key === "stats_auto_compute") {
      return "setting-stats-auto-compute";
    }
    if (key === "digest_week_start") {
      return "setting-digest-week-start";
    }
    if (key === "chart_days") {
      return "setting-chart-days";
    }
    if (key === "backup_enabled") {
      return "setting-backup-enabled";
    }
    if (key === "backup_hour_utc") {
      return "setting-backup-hour-utc";
    }
    if (key === "backup_keep_last") {
      return "setting-backup-keep-last";
    }
    if (key === "log_retention_days") {
      return "setting-log-retention-days";
    }
    return "setting-" + key.replace(/_/g, "-");
  }

  /**
   * Fill the form from a settings object.
   * @param {Object} values - Key to string map.
   */
  function fillForm(values) {
    document.getElementById(fieldId("default_tone")).value = values.default_tone || "friendly";
    document.getElementById(fieldId("brand_voice")).value = values.brand_voice || "";
    document.getElementById(fieldId("post_language")).value = values.post_language || "";
    document.getElementById(fieldId("default_hashtags")).value = values.default_hashtags || "";
    document.getElementById(fieldId("posting_enabled")).checked =
      values.posting_enabled === "true";
    document.getElementById(fieldId("posts_per_day")).value = values.posts_per_day || "1";
    postingHours = String(values.posting_hours || "")
      .split(",")
      .map(function (part) {
        return part.trim();
      })
      .filter(function (part) {
        return part.length > 0;
      });
    renderHourChips();
    document.getElementById(fieldId("dm_min_gap_seconds")).value = values.dm_min_gap_seconds || "300";
    document.getElementById(fieldId("dm_hourly_cap")).value = values.dm_hourly_cap || "10";
    document.getElementById(fieldId("dm_daily_cap")).value = values.dm_daily_cap || "20";
    document.getElementById(fieldId("reply_check_delay_hours")).value = values.reply_check_delay_hours || "6";
    document.getElementById(fieldId("reply_check_second_hours")).value = values.reply_check_second_hours || "24";
    document.getElementById(fieldId("cold_lead_days")).value = values.cold_lead_days || "3";
    document.getElementById(fieldId("follow_up_enabled")).checked =
      values.follow_up_enabled !== "false";
    document.getElementById(fieldId("max_follow_ups")).value = values.max_follow_ups || "1";
    document.getElementById(fieldId("stats_auto_compute")).checked =
      values.stats_auto_compute !== "false";
    document.getElementById(fieldId("digest_week_start")).value = values.digest_week_start || "monday";
    document.getElementById(fieldId("chart_days")).value = values.chart_days || "30";
    document.getElementById(fieldId("backup_enabled")).checked =
      values.backup_enabled !== "false";
    document.getElementById(fieldId("backup_hour_utc")).value = values.backup_hour_utc || "3";
    document.getElementById(fieldId("backup_keep_last")).value = values.backup_keep_last || "7";
    document.getElementById(fieldId("log_retention_days")).value = values.log_retention_days || "30";
  }

  /**
   * Read the form into a flat string map.
   * @returns {Object} Key to string map.
   */
  function readForm() {
    return {
      default_tone: document.getElementById(fieldId("default_tone")).value,
      brand_voice: document.getElementById(fieldId("brand_voice")).value,
      post_language: document.getElementById(fieldId("post_language")).value,
      default_hashtags: document.getElementById(fieldId("default_hashtags")).value,
      posting_enabled: document.getElementById(fieldId("posting_enabled")).checked
        ? "true"
        : "false",
      posts_per_day: document.getElementById(fieldId("posts_per_day")).value,
      posting_hours: postingHours.join(","),
      dm_min_gap_seconds: document.getElementById(fieldId("dm_min_gap_seconds")).value,
      dm_hourly_cap: document.getElementById(fieldId("dm_hourly_cap")).value,
      dm_daily_cap: document.getElementById(fieldId("dm_daily_cap")).value,
      reply_check_delay_hours: document.getElementById(fieldId("reply_check_delay_hours")).value,
      reply_check_second_hours: document.getElementById(fieldId("reply_check_second_hours")).value,
      cold_lead_days: document.getElementById(fieldId("cold_lead_days")).value,
      follow_up_enabled: document.getElementById(fieldId("follow_up_enabled")).checked
        ? "true"
        : "false",
      max_follow_ups: document.getElementById(fieldId("max_follow_ups")).value,
      stats_auto_compute: document.getElementById(fieldId("stats_auto_compute")).checked
        ? "true"
        : "false",
      digest_week_start: document.getElementById(fieldId("digest_week_start")).value,
      chart_days: document.getElementById(fieldId("chart_days")).value,
      backup_enabled: document.getElementById(fieldId("backup_enabled")).checked
        ? "true"
        : "false",
      backup_hour_utc: document.getElementById(fieldId("backup_hour_utc")).value,
      backup_keep_last: document.getElementById(fieldId("backup_keep_last")).value,
      log_retention_days: document.getElementById(fieldId("log_retention_days")).value
    };
  }

  /**
   * Clear inline field errors.
   */
  function clearErrors() {
    FIELDS.forEach(function (key) {
      var el = document.getElementById(fieldId(key) + "-error");
      if (el) {
        el.textContent = "";
        el.classList.add("hidden");
      }
    });
  }

  /**
   * Show an inline error for one field.
   * @param {string} key - Setting key.
   * @param {string} message - Error message.
   */
  function showError(key, message) {
    var el = document.getElementById(fieldId(key) + "-error");
    if (el) {
      el.textContent = message;
      el.classList.remove("hidden");
    } else {
      window.toast(message, "error");
    }
  }

  /**
   * Render posting hour chips with remove buttons.
   */
  function renderHourChips() {
    var wrap = document.getElementById("posting-hours-chips");
    wrap.innerHTML = "";
    if (postingHours.length === 0) {
      var none = document.createElement("span");
      none.className = "text-xs text-gray-400 dark:text-slate-500";
      none.textContent = "No hours set.";
      wrap.appendChild(none);
      return;
    }
    postingHours.forEach(function (hour) {
      var chip = document.createElement("span");
      chip.className = "chip";
      var label = document.createElement("span");
      label.textContent = hour;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ml-1 font-bold";
      remove.textContent = "\u00d7";
      remove.setAttribute("aria-label", "Remove hour " + hour);
      remove.addEventListener("click", function () {
        postingHours = postingHours.filter(function (item) {
          return item !== hour;
        });
        renderHourChips();
      });
      chip.appendChild(label);
      chip.appendChild(remove);
      wrap.appendChild(chip);
    });
  }

  /**
   * Format bytes as KB/MB for the backups table.
   * @param {number} size - Bytes.
   * @returns {string} Human label.
   */
  function fmtSize(size) {
    var bytes = Number(size) || 0;
    if (bytes >= 1048576) {
      return (bytes / 1048576).toFixed(1) + " MB";
    }
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  /**
   * Load the backups table.
   */
  async function loadBackups() {
    var body = document.getElementById("backups-body");
    if (!body) {
      return;
    }
    body.innerHTML = "";
    try {
      var data = await window.apiFetch("/api/system/backups");
      var items = data.items || [];
      document.getElementById("backups-empty").classList.toggle("hidden", items.length > 0);
      items.forEach(function (row) {
        var tr = document.createElement("tr");
        tr.className = "border-b border-gray-100 dark:border-slate-700";
        var dateCell = document.createElement("td");
        dateCell.className = "py-2 pr-3 text-gray-900 dark:text-slate-100";
        dateCell.textContent = row.created_at ? window.formatDate(row.created_at) : "—";
        var sizeCell = document.createElement("td");
        sizeCell.className = "py-2 pr-3 text-gray-600 dark:text-slate-300";
        sizeCell.textContent = fmtSize(row.size_bytes);
        var trigCell = document.createElement("td");
        trigCell.className = "py-2 pr-3";
        var trig = document.createElement("span");
        trig.className = "badge badge-gray";
        trig.textContent = row.trigger;
        trigCell.appendChild(trig);
        var statusCell = document.createElement("td");
        statusCell.className = "py-2 pr-3";
        var status = document.createElement("span");
        status.className = "badge " + (row.status === "ok" ? "badge-green" : "badge-red");
        status.textContent = row.status;
        statusCell.appendChild(status);
        var actionsCell = document.createElement("td");
        actionsCell.className = "py-2";
        var actions = document.createElement("div");
        actions.className = "flex flex-wrap gap-1";
        function smallBtn(label, title) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn btn-secondary btn-sm";
          btn.textContent = label;
          btn.title = title;
          return btn;
        }
        var dl = smallBtn("Download", "Download the backup file");
        dl.addEventListener("click", function () {
          window.open("/api/system/backups/" + row.id + "/download", "_blank", "noopener");
        });
        var restore = smallBtn("Restore", "Restore this backup (app restart required)");
        restore.addEventListener("click", async function () {
          var confirmed = await window.confirmDialog(
            "Restore backup " + row.filename + "? The app MUST be restarted afterwards.",
            { confirmText: "Restore", danger: true }
          );
          if (!confirmed) {
            return;
          }
          var typed = null;
          try {
            typed = window.prompt("Type RESTORE BACKUP to confirm the restore:");
          } catch (err) {
            typed = null;
          }
          if (typed !== "RESTORE BACKUP") {
            window.toast("Restore cancelled: you must type exactly RESTORE BACKUP.", "info");
            return;
          }
          try {
            var result = await window.apiFetch("/api/system/backups/" + row.id + "/restore", {
              method: "POST",
              headers: { "X-Confirm-Delete": "true" },
              body: JSON.stringify({ confirmation: "RESTORE BACKUP" })
            });
            window.toast(
              "Restored from " + result.restored_from + ". RESTART the app now.",
              "success"
            );
            loadBackups();
          } catch (err) {
            window.toast(err.message, "error");
          }
        });
        var delBtn = smallBtn("Delete", "Delete this backup");
        delBtn.addEventListener("click", async function () {
          var confirmed = await window.confirmDialog(
            "Delete backup " + row.filename + "?",
            { confirmText: "Delete", danger: true }
          );
          if (!confirmed) {
            return;
          }
          try {
            await window.apiFetch("/api/system/backups/" + row.id, {
              method: "DELETE",
              headers: { "X-Confirm-Delete": "true" }
            });
            window.toast("Backup deleted.", "success");
            loadBackups();
          } catch (err) {
            window.toast(err.message, "error");
          }
        });
        actions.appendChild(dl);
        actions.appendChild(restore);
        actions.appendChild(delBtn);
        actionsCell.appendChild(actions);
        [dateCell, sizeCell, trigCell, statusCell, actionsCell].forEach(function (cell) {
          tr.appendChild(cell);
        });
        body.appendChild(tr);
      });
    } catch (err) {
      window.toast("Could not load backups: " + err.message, "error");
    }
  }

  /**
   * Load the token expiry banner.
   */
  async function loadTokenBanner() {
    var banner = document.getElementById("token-banner");
    if (!banner) {
      return;
    }
    try {
      var status = await window.apiFetch("/api/system/token-status");
      banner.classList.remove("hidden");
      var base = "mb-3 text-sm font-medium rounded-lg px-3 py-2 ";
      if (!status.token_set || status.warning_level === "expired") {
        banner.className = base + "text-red-800 dark:text-red-200 bg-red-50/80 dark:bg-red-900/30 border border-red-200 dark:border-red-800";
        banner.textContent = "No valid Facebook token on record. Publishing will fail — set credentials and refresh below.";
      } else if (status.warning_level === "urgent") {
        banner.className = base + "text-red-800 dark:text-red-200 bg-red-50/80 dark:bg-red-900/30 border border-red-200 dark:border-red-800";
        banner.textContent = "Facebook token expires in " + status.days_left + " day(s). Refresh it now.";
      } else if (status.warning_level === "soon" && Number(status.days_left) <= 14) {
        banner.className = base + "text-amber-800 dark:text-amber-200 bg-amber-50/80 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800";
        banner.textContent = "Facebook token expires in " + status.days_left + " day(s). Plan a refresh.";
      } else if (status.warning_level === "soon") {
        banner.className = base + "text-amber-800 dark:text-amber-200 bg-amber-50/80 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800";
        banner.textContent = "Facebook token expires in " + status.days_left + " day(s).";
      } else {
        banner.className = base + "text-green-800 dark:text-green-200 bg-green-50/80 dark:bg-green-900/30 border border-green-200 dark:border-green-800";
        banner.textContent = "Facebook token healthy — " + status.days_left + " day(s) left.";
      }
    } catch (err) {
      banner.classList.remove("hidden");
      banner.className = "mb-3 text-sm font-medium rounded-lg px-3 py-2 text-gray-600 dark:text-slate-300";
      banner.textContent = "Token status unavailable.";
    }
  }

  /**
   * Load the month-to-date AI spend line.
   */
  async function loadAiSpend() {
    var line = document.getElementById("ai-spend-line");
    if (!line) {
      return;
    }
    try {
      var data = await window.apiFetch("/api/system/ai-usage?days=30");
      var mtd = data.month_to_date || {};
      var top = (data.by_provider || [])[0];
      line.textContent = (mtd.calls || 0) + " calls · $" +
        Number(mtd.cost_usd || 0).toFixed(4) + " this month" +
        (top ? " · top: " + top.provider : "");
    } catch (err) {
      line.textContent = "AI usage unavailable.";
    }
  }
  async function loadSettings() {
    var loading = document.getElementById("settings-loading");
    var errorBox = document.getElementById("settings-error");
    var content = document.getElementById("settings-content");
    loading.classList.remove("hidden");
    errorBox.classList.add("hidden");
    content.classList.add("hidden");
    try {
      var values = await window.apiFetch("/api/settings");
      fillForm(values);
      loading.classList.add("hidden");
      content.classList.remove("hidden");
    } catch (err) {
      loading.classList.add("hidden");
      document.getElementById("settings-error-text").textContent =
        "Could not load settings: " + err.message;
      errorBox.classList.remove("hidden");
    }
  }

  /**
   * Load the read-only AI provider info card.
   */
  async function loadAiInfo() {
    try {
      var data = await window.apiFetch("/api/ai/status");
      document.getElementById("ai-info-primary").textContent = data.primary_provider;
      document.getElementById("ai-info-fallback").textContent = data.fallback_provider || "\u2014";
      document.getElementById("ai-info-mock").textContent = data.mock_mode ? "on" : "off";
      document.getElementById("ai-info-groq").textContent = data.groq_configured
        ? "configured"
        : "not configured";
      document.getElementById("ai-info-openai").textContent = data.openai_configured
        ? "configured"
        : "not configured";
      document.getElementById("ai-info-loading").classList.add("hidden");
      document.getElementById("ai-info").classList.remove("hidden");
    } catch (err) {
      document.getElementById("ai-info-loading").classList.add("hidden");
      window.toast("Could not load AI status: " + err.message, "error");
    }
  }

  /**
   * Load the Facebook connection card (never displays any token).
   */
  async function loadFacebookCard() {
    try {
      var data = await window.apiFetch("/api/facebook/status");
      document.getElementById("fb-info-configured").textContent = data.configured
        ? "yes"
        : "no";
      document.getElementById("fb-info-dryrun").textContent = data.dry_run ? "on" : "off";
      document.getElementById("fb-info-token").textContent =
        data.token_valid === null || data.token_valid === undefined
          ? "unknown"
          : data.token_valid
            ? "valid"
            : "invalid";
      document.getElementById("fb-info-pageid").textContent = data.page_id || "not set";
      document.getElementById("fb-info-pagename").textContent = data.page_name || "unknown";
      var err = document.getElementById("fb-info-error");
      if (data.error) {
        err.textContent = data.error;
        err.classList.remove("hidden");
      } else {
        err.classList.add("hidden");
      }
      document.getElementById("fb-mode-dry").classList.toggle("hidden", !data.dry_run);
      document.getElementById("fb-mode-live").classList.toggle("hidden", data.dry_run);
      document.getElementById("fb-info-loading").classList.add("hidden");
      document.getElementById("fb-info").classList.remove("hidden");
    } catch (err) {
      document.getElementById("fb-info-loading").classList.add("hidden");
      window.toast("Could not load Facebook status: " + err.message, "error");
    }
  }

  /**
   * Load the Automation card.
   */
  async function loadAutomationCard() {
    try {
      var data = await window.apiFetch("/api/automation/status");
      document.getElementById("ap-info-running").textContent = data.running ? "yes" : "no";
      document.getElementById("ap-info-interval").textContent =
        String(data.interval_seconds) + "s";
      document.getElementById("ap-info-lastrun").textContent = data.last_run_at
        ? window.formatDate(data.last_run_at)
        : "never";
      var result = data.last_run_result || {};
      var bits = [];
      ["published", "failed", "skipped"].forEach(function (key) {
        if (result[key] !== undefined) {
          bits.push(key + ": " + result[key]);
        }
      });
      if (result.skipped_reason) {
        bits.push(String(result.skipped_reason));
      }
      document.getElementById("ap-info-result").textContent = bits.length
        ? bits.join(", ")
        : "no runs yet";
      document.getElementById("ap-info-nextrun").textContent = data.next_run_at
        ? window.relativeFuture(data.next_run_at)
        : "paused";
      document.getElementById("ap-loading").classList.add("hidden");
      document.getElementById("ap-info").classList.remove("hidden");
    } catch (err) {
      document.getElementById("ap-loading").classList.add("hidden");
      window.toast("Could not load Automation status: " + err.message, "error");
    }
  }

  /**
   * Handle settings form submission.
   * @param {Event} event - Submit event.
   */
  async function onSave(event) {
    event.preventDefault();
    clearErrors();
    var btn = document.getElementById("settings-save");
    window.setButtonLoading(btn, true, "Saving\u2026");
    try {
      var saved = await window.apiFetch("/api/settings", {
        method: "PUT",
        body: JSON.stringify(readForm())
      });
      fillForm(saved);
      window.toast("Settings saved.", "success");
    } catch (err) {
      if (err && err.status === 422) {
        var message = err.message || "Invalid settings.";
        var matched = FIELDS.filter(function (key) {
          return message.toLowerCase().indexOf(key.replace(/_/g, " ")) !== -1 ||
            message.toLowerCase().indexOf(key) !== -1;
        });
        if (matched.length > 0) {
          matched.forEach(function (key) {
            showError(key, message);
          });
        } else {
          window.toast(message, "error");
        }
      } else {
        window.toast(err.message, "error");
      }
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("settings-form").addEventListener("submit", onSave);
    document.getElementById("settings-retry").addEventListener("click", loadSettings);
    document.getElementById("settings-reset").addEventListener("click", loadSettings);
    document.getElementById("posting-hours-add").addEventListener("click", function () {
      var input = document.getElementById("posting-hours-input");
      var value = input.value.trim();
      if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) {
        showError("posting_hours", "Enter a valid HH:MM time.");
        return;
      }
      if (postingHours.indexOf(value) === -1) {
        postingHours.push(value);
        postingHours.sort();
        renderHourChips();
      }
      input.value = "";
    });
    loadSettings();
    loadAiInfo();
    loadFacebookCard();
    loadAutomationCard();
    loadBackups();
    loadTokenBanner();
    loadAiSpend();
    initAppearance();
    document.getElementById("backup-run-btn").addEventListener("click", async function (event) {
      var btn = event.currentTarget;
      window.setButtonLoading(btn, true, "Backing up…");
      try {
        var result = await window.apiFetch("/api/system/backups/run", { method: "POST", body: "{}" });
        window.toast("Backup saved: " + result.filename, "success");
        loadBackups();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
        // Mirror the 60s server rate limit in the UI.
        btn.disabled = true;
        setTimeout(function () {
          btn.disabled = false;
        }, 60000);
      }
    });
    document.getElementById("token-refresh-btn").addEventListener("click", async function (event) {
      var btn = event.currentTarget;
      window.setButtonLoading(btn, true, "Stamping…");
      try {
        await window.apiFetch("/api/system/token-refresh-note", { method: "POST" });
        window.toast("Token refresh recorded — 60-day clock restarted.", "success");
        loadTokenBanner();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
    });
    document.getElementById("fb-test-btn").addEventListener("click", async function (event) {
      var btn = event.currentTarget;
      window.setButtonLoading(btn, true, "Testing\u2026");
      try {
        await window.apiFetch("/api/facebook/test-connection", { method: "POST" });
        window.toast("Connection test finished.", "success");
        loadFacebookCard();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
    });
    document.getElementById("ap-run-now-btn").addEventListener("click", async function (event) {
      var btn = event.currentTarget;
      window.setButtonLoading(btn, true, "Running\u2026");
      try {
        var result = await window.apiFetch("/api/automation/run-now", { method: "POST" });
        window.toast(
          "Run finished: " + result.published + " published, " + result.failed + " failed.",
          "success"
        );
        loadAutomationCard();
      } catch (err) {
        if (err && err.status === 409) {
          window.toast("A tick is already running.", "info");
        } else {
          window.toast(err.message, "error");
        }
      } finally {
        window.setButtonLoading(btn, false);
      }
    });
    document.getElementById("ap-fill-queue-btn").addEventListener("click", async function (event) {      var btn = event.currentTarget;
      window.setButtonLoading(btn, true, "Filling\u2026");
      try {
        var filled = await window.apiFetch("/api/automation/fill-queue", { method: "POST" });
        window.toast(
          "Queue filled: " + filled.scheduled + " scheduled, " +
            filled.drafts_remaining + " drafts remaining.",
          "success"
        );
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(btn, false);
      }
    });
    document.getElementById("danger-clear-btn").addEventListener("click", function (event) {
      window.clearDummyData(event.currentTarget, function () {
        loadAutomationCard();
      });
    });
  });
})();
