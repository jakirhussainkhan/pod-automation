/* Group Lead & DM Funnel workbench: cadence timer, intent classify, leads CRUD. */
(function () {
  "use strict";

  var leadsState = { skip: 0, limit: 20, total: 0, status: "", bucket: "" };

  var STATUS_LABELS = {
    unsent: "Unsent",
    step1_sent: "Step 1 Sent",
    step2_sent: "Step 2 Sent",
    replied: "Replied",
    converted: "Converted",
    follow_up_sent: "Follow-up Sent"
  };

  /* M3 cold-lead follow-up template. Slots are filled client-side:
     {name} = lead username, {product} = attached product title (or
     "the design"), [niche] = "bike" when the group tag looks bike-ish,
     else "car". Exact copy approved by the owner. */
  var M3_TEMPLATE = "Hey {name}, quick one — I sent you info about the {product} design a few days back. Just dropped a new [niche] design you might like. Want me to send it over?";

  /**
   * Render the M3 follow-up text for a lead.
   * @param {Object} lead - Lead payload.
   * @param {string|null} productTitle - Attached product title, if known.
   * @returns {string} Personalized M3 text.
   */
  function renderM3(lead, productTitle) {
    var name = (lead.username || "friend").replace(/^@/, "");
    var product = productTitle || "the design";
    var tag = String(lead.group_name || "").toLowerCase();
    var niche = /bike|moto|harley|rider|biker|chopper|cruiser/.test(tag) ? "bike" : "car";
    return M3_TEMPLATE
      .replace("{name}", name)
      .replace("{product}", product)
      .replace("[niche]", niche);
  }

  /* ---------------- DM Safety (M1->M2 gap + quota) ---------------- */

  var dmQuota = { hourly_used: 0, hourly_limit: 10, daily_used: 0, daily_limit: 20, next_reset: null, timer: null };
  var dmGapSeconds = 300;
  var dmModal = { timer: null, leadId: null, lead: null, m2Btn: null, m2Hint: null };
  var attention = { counts: { reply_check: 0, overdue: 0, cold_followup_ready: 0, m2_waiting: 0, unassigned: 0 }, timer: null, seq: 0 };
  var selectedLeads = {};
  var snapshot = { timer: null, seq: 0, data: null };
  var accountsById = {};
  var accountsList = [];

  /**
   * Format seconds as "M:SS" countdown.
   * @param {number} total - Seconds remaining.
   * @returns {string} Countdown label.
   */
  function fmtCountdown(total) {
    var t = Math.max(0, Math.ceil(Number(total) || 0));
    var m = Math.floor(t / 60);
    var s = t % 60;
    return m + ":" + (s < 10 ? "0" + s : s);
  }

  /**
   * Describe when M1 was sent ("M1 sent 4 min ago").
   * @param {string|null} iso - ISO timestamp.
   * @returns {string} Relative label.
   */
  function m1AgoLabel(iso) {
    if (!iso) {
      return "M1 not sent";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "M1 sent time unknown";
    }
    var seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 0) {
      return "M1 sent just now";
    }
    if (seconds < 60) {
      return "M1 sent just now";
    }
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
      return "M1 sent " + minutes + (minutes === 1 ? " min ago" : " mins ago");
    }
    var hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return "M1 sent " + hours + (hours === 1 ? " hour ago" : " hours ago");
    }
    return "M1 sent " + Math.floor(hours / 24) + "d ago";
  }

  /**
   * Render the header DM quota widget.
   */
  function renderDmQuota() {
    var text = document.getElementById("dm-quota-text");
    var badge = document.getElementById("dm-quota-badge");
    if (!text || !badge) {
      return;
    }
    text.textContent =
      "DM Quota: " + dmQuota.hourly_used + "/" + dmQuota.hourly_limit +
      " this hour, " + dmQuota.daily_used + "/" + dmQuota.daily_limit + " today";
    var exhausted =
      dmQuota.hourly_used >= dmQuota.hourly_limit ||
      dmQuota.daily_used >= dmQuota.daily_limit;
    badge.className = "badge " + (exhausted ? "badge-red" : "badge-green");
    badge.textContent = exhausted ? "Rate Limited" : "OK";
  }

  /**
   * Load quota counters + gap config (best-effort, keeps defaults offline).
   */
  async function loadDmQuota() {
    try {
      var data = await window.apiFetch("/api/dm-safety/status");
      dmQuota.hourly_used = Number(data.hourly_used) || 0;
      dmQuota.hourly_limit = Number(data.hourly_limit) || 10;
      dmQuota.daily_used = Number(data.daily_used) || 0;
      dmQuota.daily_limit = Number(data.daily_limit) || 20;
      dmQuota.next_reset = data.next_hourly_reset_at || null;
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("DM quota unavailable:", err && err.message);
      }
    }
    renderDmQuota();
  }

  /**
   * Load the configured M1->M2 gap for client-side pills.
   */
  async function loadDmGap() {
    try {
      var settings = await window.apiFetch("/api/settings");
      var gap = Number(settings.dm_min_gap_seconds);
      if (gap >= 60) {
        dmGapSeconds = gap;
      }
    } catch (err) {
      /* Keep default 300s offline. */
    }
  }

  /**
   * Load the account directory for badges + the DM modal dropdown.
   */
  async function loadAccountsBrief() {
    try {
      var data = await window.apiFetch("/api/accounts?include_inactive=true");
      accountsList = data.items || [];
      accountsById = {};
      accountsList.forEach(function (account) {
        accountsById[account.id] = account;
      });
    } catch (err) {
      accountsList = [];
      accountsById = {};
    }
  }

  /**
   * Account badge for a lead row ("@handle" or "unassigned").
   * @param {Object} lead - Lead payload.
   * @returns {HTMLSpanElement} Badge.
   */
  function accountBadge(lead) {
    var badge = document.createElement("span");
    var account = lead.assigned_account_id ? accountsById[lead.assigned_account_id] : null;
    if (account) {
      badge.className = "badge badge-blue";
      badge.textContent = "@" + (account.handle || account.persona_name || account.name);
      badge.title = "Assigned to " + account.name;
    } else {
      badge.className = "badge badge-gray";
      badge.textContent = "unassigned";
      badge.title = "No account assigned yet.";
    }
    return badge;
  }

  /**
   * Render the Attention Board tiles + urgency badge.
   */
  function renderAttention() {
    var counts = attention.counts || {};
    var reply = Number(counts.reply_check) || 0;
    var overdue = Number(counts.overdue) || 0;
    var m2w = Number(counts.m2_waiting) || 0;
    var cold = Number(counts.cold_followup_ready) || 0;
    var unassigned = Number(counts.unassigned) || 0;
    var el = function (id) {
      return document.getElementById(id);
    };
    if (el("attention-reply-check")) {
      el("attention-reply-check").textContent = String(reply);
    }
    if (el("attention-overdue")) {
      el("attention-overdue").textContent = String(overdue);
    }
    if (el("attention-m2-waiting")) {
      el("attention-m2-waiting").textContent = String(m2w);
    }
    if (el("attention-cold")) {
      el("attention-cold").textContent = String(cold);
    }
    if (el("attention-unassigned")) {
      el("attention-unassigned").textContent = String(unassigned);
    }
    var badge = el("attention-badge");
    if (badge) {
      var hot = overdue > 0 || m2w > 0;
      var total = reply + overdue + m2w + cold + unassigned;
      badge.className = "badge " + (hot ? "badge-red" : total > 0 ? "badge-amber" : "badge-green");
      badge.textContent = hot ? "Action needed" : total > 0 ? total + " pending" : "All clear";
    }
  }

  /**
   * Load bucketed attention counts (request-seq guarded against races).
   */
  async function loadAttention() {
    var mySeq = ++attention.seq;
    try {
      var data = await window.apiFetch("/api/group-leads/attention");
      if (mySeq !== attention.seq) {
        return; // A newer poll already superseded this response.
      }
      attention.counts = data.counts || {};
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Attention board unavailable:", err && err.message);
      }
    }
    if (mySeq === attention.seq) {
      renderAttention();
    }
  }

  /**
   * Set the lead-list bucket filter (persisted) and refetch page one.
   * @param {string} bucket - "" | reply_check | overdue | m2_waiting | cold.
   */
  function setBucket(bucket) {
    leadsState.bucket = bucket || "";
    try {
      sessionStorage.setItem("groups-bucket", leadsState.bucket);
    } catch (err) {
      /* Storage unavailable: filter still applies for this session. */
    }
    if (bucket === "__converted") {
      leadsState.bucket = "";
      leadsState.status = "converted";
      document.getElementById("leads-filter").value = "converted";
    }
    leadsState.skip = 0;
    syncBucketChips();
    loadLeads();
  }

  /**
   * Highlight the active filter chip.
   */
  function syncBucketChips() {
    var chips = document.querySelectorAll("#leads-chips .bucket-chip");
    Array.prototype.forEach.call(chips, function (chip) {
      var value = chip.getAttribute("data-bucket");
      var active = value === (leadsState.bucket || "") ||
        (value === "__converted" && !leadsState.bucket && leadsState.status === "converted");
      chip.classList.toggle("pill-active", !!active);
      chip.setAttribute("aria-pressed", active ? "true" : "false");
    });
    Array.prototype.forEach.call(
      document.querySelectorAll("#attention-board .attention-tile"),
      function (tile) {
        var active = tile.getAttribute("data-bucket") === (leadsState.bucket || "");
        tile.classList.toggle("btn-primary", !!active);
        tile.classList.toggle("btn-secondary", !active);
      }
    );
  }
  function dmReadinessPill(lead) {
    var pill = document.createElement("span");
    var quotaHit =
      dmQuota.hourly_used >= dmQuota.hourly_limit ||
      dmQuota.daily_used >= dmQuota.daily_limit;
    if (lead.status === "step1_sent" && lead.step1_sent_at) {
      var sent = new Date(lead.step1_sent_at).getTime();
      var elapsed = (Date.now() - sent) / 1000;
      if (quotaHit) {
        pill.className = "badge badge-red";
        pill.textContent = "Rate Limited";
        pill.title = "Quota exhausted — M2 blocked until reset.";
      } else if (elapsed >= dmGapSeconds) {
        pill.className = "badge badge-green";
        pill.textContent = "M2 Ready";
        pill.title = "Gap elapsed — safe to send Message 2.";
      } else {
        pill.className = "badge badge-amber";
        pill.textContent = "Waiting (" + fmtCountdown(dmGapSeconds - elapsed) + ")";
        pill.title = "M1->M2 safety gap still counting down.";
      }
    } else if (lead.status === "step2_sent" || lead.status === "replied" || lead.status === "converted") {
      pill.className = "badge badge-green";
      pill.textContent = "M2 Sent";
      pill.title = "Message 2 already sent.";
    } else {
      pill.className = "badge badge-gray";
      pill.textContent = "No M1";
      pill.title = "Send Message 1 first.";
    }
    return pill;
  }

  /**
   * Format an ISO timestamp as local HH:MM for reset-time toasts.
   * @param {string|null} iso - ISO timestamp.
   * @returns {string} HH:MM label or fallback.
   */
  function fmtResetTime(iso) {
    if (!iso) {
      return "the next hour";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "the next hour";
    }
    var h = date.getHours();
    var m = date.getMinutes();
    return (h < 10 ? "0" + h : "" + h) + ":" + (m < 10 ? "0" + m : "" + m);
  }

  /* ---------------- Cadence Helper Widget ---------------- */

  var cadence = { delay: 0, remaining: 0, timer: null };

  /**
   * Format seconds as "Mm SSs".
   * @param {number} total - Seconds.
   * @returns {string} Label.
   */
  function fmtDelay(total) {
    var m = Math.floor(total / 60);
    var s = total % 60;
    return m + "m " + (s < 10 ? "0" + s : s) + "s";
  }

  /**
   * Render cadence status text + progress bar.
   */
  function renderCadence() {
    var label = document.getElementById("cadence-delay-label");
    var status = document.getElementById("cadence-status");
    var bar = document.getElementById("cadence-progress");
    var startBtn = document.getElementById("cadence-start-btn");
    if (cadence.delay > 0) {
      label.textContent = "Safety delay: " + fmtDelay(cadence.delay);
    } else {
      label.textContent = "—";
    }
    if (cadence.remaining > 0) {
      status.textContent = "⏳ WAIT — do NOT post or reply yet. Safe in " + fmtDelay(cadence.remaining) + ".";
      status.className = "text-sm font-bold text-red-600 dark:text-red-300";
      var done = cadence.delay - cadence.remaining;
      bar.style.width = Math.round((done / cadence.delay) * 100) + "%";
      startBtn.disabled = true;
    } else if (cadence.delay > 0 && cadence.finished) {
      status.textContent = "✅ SAFE — you may now post or reply in the next group.";
      status.className = "text-sm font-bold text-green-700 dark:text-green-300";
      bar.style.width = "100%";
      startBtn.disabled = false;
    } else if (cadence.delay > 0) {
      status.textContent = "Ready: post/reply once, then press Start Countdown.";
      status.className = "text-sm font-medium text-gray-600 dark:text-slate-300";
      bar.style.width = "0%";
      startBtn.disabled = false;
    } else {
      status.textContent = "Press “Roll Safety Delay”, post/reply, then start the timer.";
      bar.style.width = "0%";
    }
  }

  /**
   * Tick the countdown once per second.
   */
  function tickCadence() {
    cadence.remaining -= 1;
    if (cadence.remaining <= 0) {
      cadence.remaining = 0;
      cadence.finished = true;
      if (cadence.timer) {
        clearInterval(cadence.timer);
        cadence.timer = null;
      }
      try {
        if (navigator.vibrate) {
          navigator.vibrate(200);
        }
      } catch (e) {
        /* Vibration unsupported: ignore. */
      }
      window.toast("Safe to post — cadence delay elapsed.", "success");
    }
    renderCadence();
  }

  /* ---------------- Intent classify ---------------- */

  /**
   * Read intent form values.
   * @returns {Object} Form payload.
   */
  function intentForm() {
    return {
      username: document.getElementById("intent-username").value.trim() || "group_member",
      group_name: document.getElementById("intent-group").value.trim() || null,
      comment_text: document.getElementById("intent-comment").value.trim(),
      product_id: document.getElementById("intent-product").value
        ? Number(document.getElementById("intent-product").value)
        : null
    };
  }

  /**
   * Render an intent classification result box.
   * @param {Object} data - Classify response.
   */
  function renderIntent(data) {
    var box = document.getElementById("intent-result");
    box.classList.remove("hidden");
    var color =
      data.intent === "high"
        ? "badge-green"
        : data.intent === "medium"
          ? "badge-amber"
          : "badge-gray";
    box.className =
      "text-sm rounded-lg border px-4 py-3 border-gray-200 dark:border-slate-700";
    box.innerHTML = "";
    var badge = document.createElement("span");
    badge.className = "badge " + color;
    badge.textContent = data.intent.toUpperCase() + " intent · " + Math.round((data.confidence || 0) * 100) + "%";
    box.appendChild(badge);
    if (data.signals && data.signals.length) {
      var sig = document.createElement("p");
      sig.className = "mt-2 text-xs text-gray-500 dark:text-slate-400";
      sig.textContent = "Signals: " + data.signals.join(", ");
      box.appendChild(sig);
    }
    if (data.intent === "high" && data.message1) {
      var m1 = document.createElement("p");
      m1.className = "mt-2 text-gray-800 dark:text-slate-100 whitespace-pre-wrap";
      m1.textContent = "Message 1 (no link): " + data.message1;
      box.appendChild(m1);
      var m2 = document.createElement("p");
      m2.className = "mt-1 text-gray-600 dark:text-slate-300 whitespace-pre-wrap";
      m2.textContent = "Message 2 (link follow-up): " + (data.message2 || "—");
      box.appendChild(m2);
    } else if (data.intent !== "high") {
      var hint = document.createElement("p");
      hint.className = "mt-2 text-gray-600 dark:text-slate-300";
      hint.textContent =
        data.intent === "medium"
          ? "Medium intent: engage warmly in comments; save the DM funnel for buying signals."
          : "Low intent: no DM needed — keep nurturing with link-free engagement posts.";
      box.appendChild(hint);
    }
  }

  /* ---------------- Leads table ---------------- */

  /**
   * Badge HTML for intent values.
   * @param {string} intent - Intent value.
   * @returns {string} Badge class.
   */
  function intentBadge(intent) {
    if (intent === "high") {
      return "badge-green";
    }
    if (intent === "medium") {
      return "badge-amber";
    }
    return "badge-gray";
  }

  /**
   * Load funnel stat cards.
   */
  async function loadStats() {
    try {
      var stats = await window.apiFetch("/api/groups/funnel/stats");
      document.getElementById("funnel-total").textContent = stats.total || 0;
      document.getElementById("funnel-unsent").textContent = stats.unsent || 0;
      document.getElementById("funnel-step1").textContent = stats.step1_sent || 0;
      document.getElementById("funnel-converted").textContent = stats.converted || 0;
    } catch (err) {
      /* Stats are best-effort: keep zeros, warn for diagnostics. */
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Funnel stats unavailable:", err && err.message);
      }
    }
  }

  /**
   * Load leads page into the table.
   */
  async function loadLeads() {
    var body = document.getElementById("leads-body");
    body.innerHTML = "";
    document.getElementById("leads-empty").classList.add("hidden");
    var qs = "?skip=" + leadsState.skip + "&limit=" + leadsState.limit;
    if (leadsState.status) {
      qs += "&status=" + encodeURIComponent(leadsState.status);
    }
    if (leadsState.bucket) {
      qs += "&bucket=" + encodeURIComponent(leadsState.bucket);
    }
    try {
      var data = await window.apiFetch("/api/group-leads" + qs);
      leadsState.total = data.total || 0;
      if (!data.items || data.items.length === 0) {
        document.getElementById("leads-empty").classList.remove("hidden");
      }
      (data.items || []).forEach(function (lead) {
        body.appendChild(leadRow(lead));
      });
      window.renderPagination(
        document.getElementById("leads-pagination"),
        { total: data.total, skip: data.skip, limit: data.limit },
        function (nextSkip) {
          leadsState.skip = nextSkip;
          loadLeads();
        }
      );
    } catch (err) {
      window.toast("Could not load leads: " + err.message, "error");
    }
    updateBulkBar();
    loadStats();
  }

  /**
   * Build a table row for a lead.
   * @param {Object} lead - Lead payload.
   * @returns {HTMLTableRowElement} Row element.
   */
  function leadRow(lead) {
    var tr = document.createElement("tr");
    tr.className = "border-b border-gray-100 dark:border-slate-700";
    tr.dataset.leadId = String(lead.id);

    var checkCell = document.createElement("td");
    checkCell.className = "py-2 pr-2 align-top";
    var checkBox = document.createElement("input");
    checkBox.type = "checkbox";
    checkBox.className = "lead-select";
    checkBox.value = String(lead.id);
    checkBox.checked = !!selectedLeads[lead.id];
    checkBox.setAttribute("aria-label", "Select lead " + lead.id);
    checkBox.addEventListener("change", function () {
      if (checkBox.checked) {
        selectedLeads[lead.id] = true;
      } else {
        delete selectedLeads[lead.id];
      }
      updateBulkBar();
    });
    checkCell.appendChild(checkBox);
    tr.appendChild(checkCell);

    var userCell = document.createElement("td");
    userCell.className = "py-2 pr-3 align-top";
    var name = document.createElement("p");
    name.className = "font-semibold text-gray-900 dark:text-slate-100";
    name.textContent = "@" + lead.username + (lead.group_name ? " · " + lead.group_name : "");
    var acctWrap = document.createElement("p");
    acctWrap.className = "mt-1";
    acctWrap.appendChild(accountBadge(lead));
    var comment = document.createElement("p");
    comment.className = "text-xs text-gray-600 dark:text-slate-300 mt-1 clamp-4";
    comment.textContent = lead.comment_text;
    userCell.appendChild(name);
    userCell.appendChild(acctWrap);
    userCell.appendChild(comment);
    if (lead.user_profile_link) {
      var profile = document.createElement("a");
      profile.href = lead.user_profile_link;
      profile.target = "_blank";
      profile.rel = "noopener";
      profile.className = "text-xs text-gray-700 dark:text-slate-200 font-medium underline";
      profile.textContent = "Profile ↗";
      userCell.appendChild(profile);
    }
    tr.appendChild(userCell);

    var intentCell = document.createElement("td");
    intentCell.className = "py-2 pr-3 align-top";
    var badge = document.createElement("span");
    badge.className = "badge " + intentBadge(lead.intent);
    badge.textContent = lead.intent;
    intentCell.appendChild(badge);
    var readinessWrap = document.createElement("p");
    readinessWrap.className = "mt-1";
    readinessWrap.appendChild(dmReadinessPill(lead));
    intentCell.appendChild(readinessWrap);
    tr.appendChild(intentCell);

    var statusCell = document.createElement("td");
    statusCell.className = "py-2 pr-3 align-top";
    var select = document.createElement("select");
    select.className = "field-input";
    select.style.width = "auto";
    select.setAttribute("aria-label", "Lead " + lead.id + " status");
    Object.keys(STATUS_LABELS).forEach(function (key) {
      var opt = document.createElement("option");
      opt.value = key;
      opt.textContent = STATUS_LABELS[key];
      if (lead.status === key) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
    select.addEventListener("change", async function () {
      try {
        var patched = await window.apiFetch("/api/group-leads/" + lead.id, {
          method: "PATCH",
          body: JSON.stringify({ status: select.value })
        });
        lead.status = patched.status;
        lead.step1_sent_at = patched.step1_sent_at;
        lead.step2_sent_at = patched.step2_sent_at;
        window.toast("Lead " + lead.id + " → " + STATUS_LABELS[select.value], "success");
        loadStats();
        loadDmQuota();
        loadLeads();
      } catch (err) {
        if (err && err.status === 409) {
          window.toast("Too early: " + err.message, "info");
        } else if (err && err.status === 429) {
          window.toast("Hourly DM limit reached. Wait until " + fmtResetTime(dmQuota.next_reset) + ".", "error");
        } else {
          window.toast(err.message, "error");
        }
        select.value = lead.status;
      }
    });
    statusCell.appendChild(select);
    var urgency = lead.urgency || null;
    if (urgency && urgency.suggested_action === "send_followup") {
      var coldPill = document.createElement("p");
      coldPill.className = "mt-1";
      var coldChip = document.createElement("span");
      coldChip.className = "badge badge-blue";
      coldChip.textContent = "Send Follow-up";
      coldChip.title = "Cold lead — M3 follow-up is ready.";
      coldPill.appendChild(coldChip);
      statusCell.appendChild(coldPill);
    } else if (urgency && urgency.is_overdue) {
      var overPill = document.createElement("p");
      overPill.className = "mt-1";
      var overChip = document.createElement("span");
      overChip.className = "badge badge-red";
      overChip.textContent = "Overdue — Check Now";
      overChip.title = "No reply state recorded for 24h+.";
      overPill.appendChild(overChip);
      statusCell.appendChild(overPill);
    } else if (urgency && urgency.needs_reply_check) {
      var checkPill = document.createElement("p");
      checkPill.className = "mt-1";
      var checkChip = document.createElement("span");
      checkChip.className = "badge badge-amber";
      checkChip.textContent = "Check Reply";
      checkChip.title = "M1 is aging — verify whether they replied.";
      checkPill.appendChild(checkChip);
      statusCell.appendChild(checkPill);
    }
    if (lead.conversion_value && Number(lead.conversion_value) > 0) {
      var valueBadge = document.createElement("p");
      valueBadge.className = "mt-1";
      var valueChip = document.createElement("span");
      valueChip.className = "badge badge-green";
      valueChip.textContent = "$" + Number(lead.conversion_value).toFixed(2);
      valueBadge.appendChild(valueChip);
      statusCell.appendChild(valueBadge);
    }
    tr.appendChild(statusCell);

    var dmCell = document.createElement("td");
    dmCell.className = "py-2 pr-3 align-top";
    var viewBtn = document.createElement("button");
    viewBtn.type = "button";
    viewBtn.className = "btn btn-secondary btn-sm";
    viewBtn.textContent = lead.intent === "high" ? "View DMs" : "—";
    viewBtn.disabled = lead.intent !== "high";
    viewBtn.addEventListener("click", function () {
      openDmModal(lead);
    });
    dmCell.appendChild(viewBtn);
    var rowUrgency = lead.urgency || null;
    if (rowUrgency && (rowUrgency.needs_reply_check || rowUrgency.is_overdue || rowUrgency.m2_waiting)) {
      var checkReplyBtn = document.createElement("button");
      checkReplyBtn.type = "button";
      checkReplyBtn.className = "btn btn-secondary btn-sm ml-1";
      checkReplyBtn.textContent = "Check Reply";
      checkReplyBtn.setAttribute("title", "Record whether this lead replied in Messenger");
      checkReplyBtn.addEventListener("click", function () {
        openCheckReplyModal(lead);
      });
      dmCell.appendChild(checkReplyBtn);
    }
    if (rowUrgency && rowUrgency.follow_up_ready) {
      var followUpBtn = document.createElement("button");
      followUpBtn.type = "button";
      followUpBtn.className = "btn btn-primary btn-sm ml-1";
      followUpBtn.textContent = "Follow-up";
      followUpBtn.setAttribute("title", "Send the M3 cold-lead follow-up");
      followUpBtn.addEventListener("click", function () {
        sendFollowUp(lead);
      });
      dmCell.appendChild(followUpBtn);
    }
    tr.appendChild(dmCell);

    var actionsCell = document.createElement("td");
    actionsCell.className = "py-2 align-top";
    var actionsWrap = document.createElement("div");
    actionsWrap.className = "flex flex-wrap gap-1";
    var copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "btn btn-secondary btn-sm";
    copyBtn.textContent = "Copy M1";
    copyBtn.disabled = !lead.message1;
    copyBtn.addEventListener("click", async function () {
      var ok = await window.copyToClipboard(lead.message1);
      window.toast(ok ? "Message 1 copied (no link — safe to send)." : "Copy failed.", ok ? "success" : "error");
    });
    var outreachBtn = document.createElement("button");
    outreachBtn.type = "button";
    outreachBtn.className = "btn btn-primary btn-sm";
    outreachBtn.textContent = "Copy M1 & Open DM";
    outreachBtn.disabled = !lead.message1;
    outreachBtn.setAttribute("title", "Copy Message 1 and open the lead's Facebook profile in a new tab");
    outreachBtn.addEventListener("click", async function () {
      var ok = await window.copyToClipboard(lead.message1);
      if (!ok) {
        window.toast("Copy failed.", "error");
        return;
      }
      var target = lead.user_profile_link ||
        "https://www.facebook.com/search/top?q=" + encodeURIComponent(lead.username);
      window.open(target, "_blank", "noopener");
      window.toast("Message 1 copied — paste it into the opened chat, then mark Step 1 Sent.", "success");
    });
    var delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn btn-secondary btn-sm";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", async function () {
      var confirmed = await window.confirmDialog("Delete lead " + lead.id + " (" + lead.username + ")?", { danger: true, confirmText: "Delete" });
      if (!confirmed) {
        return;
      }
      try {
        await window.apiFetch("/api/group-leads/" + lead.id, { method: "DELETE" });
        window.toast("Lead deleted.", "success");
        loadLeads();
      } catch (err) {
        window.toast(err.message, "error");
      }
    });
    actionsWrap.appendChild(copyBtn);
    actionsWrap.appendChild(outreachBtn);
    actionsWrap.appendChild(delBtn);
    actionsCell.appendChild(actionsWrap);
    tr.appendChild(actionsCell);
    return tr;
  }

  /**
   * Render the Today's Snapshot mini-card from cached snapshot data.
   */
  function renderSnapshot() {
    var values = document.getElementById("snapshot-values");
    var auto = document.getElementById("snapshot-auto");
    var logBtn = document.getElementById("snapshot-log-btn");
    var editBtn = document.getElementById("snapshot-edit-btn");
    if (!values || !snapshot.data) {
      return;
    }
    var d = snapshot.data;
    var logged = (Number(d.member_count) || 0) > 0 ||
      (Number(d.new_members) || 0) > 0 ||
      (Number(d.comments_received) || 0) > 0 || !!d.notes;
    values.textContent = logged
      ? "Members " + d.member_count + " · New " + d.new_members +
        " · Posts " + d.posts_published + " · Leads " + d.leads_captured +
        " · Converted " + d.converted + " · $" + Number(d.revenue || 0).toFixed(2)
      : "Not logged yet — auto: " + d.leads_captured + " leads, " +
        d.m1_sent + " M1, " + d.m2_sent + " M2, " + d.converted + " converted.";
    if (auto) {
      auto.textContent = "Auto: " + d.leads_captured + " leads, " + d.m1_sent +
        " M1, " + d.m2_sent + " M2, " + d.converted + " converted.";
      auto.classList.remove("hidden");
    }
    if (logBtn) {
      logBtn.classList.toggle("hidden", logged);
    }
    if (editBtn) {
      editBtn.classList.toggle("hidden", !logged);
    }
  }

  /**
   * Load today's snapshot (request-seq guarded against races).
   */
  async function loadSnapshot() {
    var mySeq = ++snapshot.seq;
    try {
      var data = await window.apiFetch("/api/stats/today");
      if (mySeq !== snapshot.seq) {
        return;
      }
      snapshot.data = data;
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Snapshot unavailable:", err && err.message);
      }
    }
    if (mySeq === snapshot.seq) {
      renderSnapshot();
    }
  }

  /**
   * Open the Log Stats modal (generic-modal) with 6 numeric inputs.
   */
  function openLogStatsModal() {
    var d = snapshot.data || {};
    document.getElementById("generic-modal-title").textContent = "Log Today's Numbers";
    var modalBody = document.getElementById("generic-modal-body");
    modalBody.innerHTML = "";
    var autoLine = document.createElement("p");
    autoLine.className = "text-xs text-gray-500 dark:text-slate-400 mb-3";
    autoLine.textContent = "Auto: " + (d.leads_captured || 0) + " leads, " +
      (d.m1_sent || 0) + " M1, " + (d.m2_sent || 0) + " M2, " +
      (d.converted || 0) + " converted. Manual fields below are yours to fill.";
    modalBody.appendChild(autoLine);
    var grid = document.createElement("div");
    grid.className = "grid grid-cols-2 gap-3";
    var inputs = {};
    [
      { key: "member_count", label: "Members", value: d.member_count },
      { key: "new_members", label: "New members", value: d.new_members },
      { key: "posts_published", label: "Posts published", value: d.posts_published },
      { key: "comments_received", label: "Comments received", value: d.comments_received },
      { key: "leads_captured", label: "Leads captured", value: d.leads_captured },
      { key: "revenue", label: "Revenue ($)", value: d.revenue, step: "0.01" }
    ].forEach(function (field) {
      var wrap = document.createElement("div");
      var label = document.createElement("label");
      label.className = "field-label";
      label.textContent = field.label;
      var input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.step = field.step || "1";
      input.className = "field-input";
      input.id = "stat-input-" + field.key;
      label.setAttribute("for", input.id);
      input.value = field.value === null || field.value === undefined ? "" : String(field.value);
      inputs[field.key] = input;
      wrap.appendChild(label);
      wrap.appendChild(input);
      grid.appendChild(wrap);
    });
    modalBody.appendChild(grid);
    var notesLabel = document.createElement("label");
    notesLabel.className = "field-label mt-3";
    notesLabel.textContent = "Notes (optional)";
    var notes = document.createElement("textarea");
    notes.id = "stat-notes";
    notesLabel.setAttribute("for", notes.id);
    notes.className = "field-input";
    notes.rows = 2;
    notes.value = d.notes || "";
    modalBody.appendChild(notesLabel);
    modalBody.appendChild(notes);
    var save = document.createElement("button");
    save.type = "button";
    save.className = "btn btn-primary mt-4";
    save.textContent = "Save Snapshot";
    save.addEventListener("click", async function () {
      var payload = {};
      var bad = null;
      Object.keys(inputs).forEach(function (key) {
        var raw = inputs[key].value.trim();
        if (raw === "") {
          return;
        }
        var number = Number(raw);
        if (isNaN(number) || number < 0) {
          bad = key;
        } else {
          payload[key] = number;
        }
      });
      if (bad) {
        window.toast("Enter a number of 0 or more for " + bad + ".", "error");
        return;
      }
      if (notes.value.trim()) {
        payload.notes = notes.value.trim();
      }
      window.setButtonLoading(save, true, "Saving…");
      try {
        await window.apiFetch("/api/stats/daily", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        window.toast("Today's numbers saved.", "success");
        window.closeModal("generic-modal");
        loadSnapshot();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(save, false);
      }
    });
    modalBody.appendChild(save);
    window.openModal("generic-modal");
  }

  /**
   * Refresh the bulk-action bar from the current row selection.
   */
  function updateBulkBar() {
    var bar = document.getElementById("leads-bulk-bar");
    var count = document.getElementById("leads-bulk-count");
    if (!bar || !count) {
      return;
    }
    var ids = Object.keys(selectedLeads);
    if (ids.length === 0) {
      bar.classList.add("hidden");
    } else {
      bar.classList.remove("hidden");
      bar.classList.add("flex");
      count.textContent = ids.length + " selected";
    }
    var selectAll = document.getElementById("leads-select-all");
    if (selectAll) {
      var boxes = document.querySelectorAll("#leads-body .lead-select");
      selectAll.checked = boxes.length > 0 &&
        Array.prototype.every.call(boxes, function (box) {
          return box.checked;
        });
    }
  }

  /**
   * Fetch an attached product title for M3 personalization (best-effort).
   * @param {number|null} productId - Product id or null.
   * @returns {Promise<string|null>} Title or null when unknown.
   */
  async function fetchProductTitle(productId) {
    if (!productId) {
      return null;
    }
    try {
      var product = await window.apiFetch("/api/products/" + productId);
      return product.title || null;
    } catch (err) {
      return null;
    }
  }

  /**
   * Open the lightweight Check-Reply modal for a lead.
   * @param {Object} lead - Lead payload.
   */
  function openCheckReplyModal(lead) {
    clearDmModalPoll();
    var titleEl = document.getElementById("generic-modal-title");
    titleEl.textContent = "Check Reply — @" + lead.username;
    var modalBody = document.getElementById("generic-modal-body");
    modalBody.innerHTML = "";
    var hint = document.createElement("p");
    hint.className = "text-sm text-gray-600 dark:text-slate-300 mb-4";
    hint.textContent = "Open the Messenger thread with @" + lead.username +
      ", see whether they replied to Message 1, then record the outcome:";
    modalBody.appendChild(hint);
    var row = document.createElement("div");
    row.className = "flex flex-col sm:flex-row gap-2";
    [
      { state: "replied", label: "✅ Replied — Unlock M2", cls: "btn btn-primary", toast: "Marked as replied — M2 is now sendable after the safety gap." },
      { state: "no_reply", label: "❌ No Reply Yet", cls: "btn btn-secondary", toast: "Marked as no reply — follow-up will unlock when cold." },
      { state: "bounced", label: "⛔ Bounced/Not Found", cls: "btn btn-secondary", toast: "Marked as bounced." }
    ].forEach(function (opt) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = opt.cls;
      btn.textContent = opt.label;
      btn.addEventListener("click", async function () {
        window.setButtonLoading(btn, true, "Saving…");
        try {
          var updated = await window.apiFetch("/api/group-leads/" + lead.id + "/mark-reply", {
            method: "POST",
            body: JSON.stringify({ reply_state: opt.state })
          });
          lead.reply_state = updated.reply_state;
          lead.last_checked_at = updated.last_checked_at;
          lead.urgency = updated.urgency;
          window.toast(opt.toast, "success");
          window.closeModal("generic-modal");
          loadLeads();
          loadAttention();
        } catch (err) {
          window.toast(err.message, "error");
        } finally {
          window.setButtonLoading(btn, false);
        }
      });
      row.appendChild(btn);
    });
    modalBody.appendChild(row);
    var openThread = document.createElement("button");
    openThread.type = "button";
    openThread.className = "btn btn-secondary btn-sm mt-4";
    openThread.textContent = "Open Facebook Profile";
    openThread.addEventListener("click", function () {
      var target = lead.user_profile_link ||
        "https://www.facebook.com/search/top?q=" + encodeURIComponent(lead.username);
      window.open(target, "_blank", "noopener");
    });
    modalBody.appendChild(openThread);
    window.openModal("generic-modal");
  }

  /**
   * Run the Send Follow-up flow: confirm → POST → copy M3 + open profile.
   * @param {Object} lead - Lead payload.
   */
  async function sendFollowUp(lead) {
    var count = Number(lead.follow_up_count) || 0;
    var confirmed = await window.confirmDialog(
      "Send follow-up message to " + lead.username + "? This is message #" + (count + 1) + ".",
      { confirmText: "Send Follow-up" }
    );
    if (!confirmed) {
      return;
    }
    try {
      var result = await window.apiFetch("/api/group-leads/" + lead.id + "/follow-up", {
        method: "POST"
      });
      var title = await fetchProductTitle(lead.product_id);
      var m3 = renderM3(lead, title);
      var copied = await window.copyToClipboard(m3);
      var target = lead.user_profile_link ||
        "https://www.facebook.com/search/top?q=" + encodeURIComponent(lead.username);
      window.open(target, "_blank", "noopener");
      var quota = result.quota || {};
      window.toast(
        "Follow-up sent" + (copied ? " (M3 copied — paste it into the chat)." : ".") +
        " Counters: " + (quota.hourly_used || "?") + "/" + (quota.hourly_limit || "?") + " this hour.",
        "success"
      );
      loadLeads();
      loadAttention();
      loadDmQuota();
    } catch (err) {
      if (err && err.status === 429) {
        window.toast("Hourly DM limit reached. Wait until " + fmtResetTime(dmQuota.next_reset) + ".", "error");
      } else {
        window.toast(err.message, err && err.status === 409 ? "info" : "error");
      }
    }
  }

  /**
   * Clear the DM modal send-status poll timer.
   */
  function clearDmModalPoll() {
    if (dmModal.timer) {
      clearInterval(dmModal.timer);
      dmModal.timer = null;
    }
    dmModal.leadId = null;
  }

  /**
   * Close the DM modal and stop its poll timer.
   */
  function closeDmModal() {
    clearDmModalPoll();
    window.closeModal("generic-modal");
  }

  /**
   * Refresh the M2 button from live send-status (no state change).
   */
  async function refreshDmModalState() {
    if (!dmModal.leadId || !dmModal.m2Btn) {
      return;
    }
    // If the modal was closed (backdrop/Escape), stop polling.
    var backdrop = document.getElementById("generic-modal");
    if (!backdrop || backdrop.hidden) {
      clearDmModalPoll();
      return;
    }
    try {
      var state = await window.apiFetch("/api/group-leads/" + dmModal.leadId + "/send-status");
      var btn = dmModal.m2Btn;
      var hint = dmModal.m2Hint;
      if (!state.rate_limit_ok) {
        btn.disabled = true;
        btn.textContent = "Send M2 (Rate limited)";
        if (hint) {
          hint.textContent = state.rate_limit_reason + ". Resets at " + fmtResetTime(dmQuota.next_reset) + ".";
        }
        return;
      }
      if (state.can_send_m2) {
        btn.disabled = false;
        btn.textContent = "Send M2 (Ready)";
        if (hint) {
          hint.textContent = "Gap elapsed and quota available — safe to send Message 2.";
        }
      } else {
        btn.disabled = true;
        btn.textContent = "Send M2 (Locked)";
        if (hint) {
          var secs = Number(state.seconds_until_m2) || 0;
          hint.textContent = secs > 0 ? "Wait " + fmtCountdown(secs) + " before sending M2." : state.reason;
        }
      }
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Send-status unavailable:", err && err.message);
      }
    }
  }

  /**
   * Open the shared modal showing both DM messages with copy buttons.
   * @param {Object} lead - Lead payload.
   */
  function openDmModal(lead) {
    clearDmModalPoll();
    dmModal.leadId = lead.id;
    dmModal.lead = lead;
    var titleEl = document.getElementById("generic-modal-title");
    titleEl.textContent = "DM Funnel — @" + lead.username + " (" + lead.intent + ")";
    var m1Badge = document.createElement("span");
    m1Badge.className = "badge badge-gray ml-2";
    m1Badge.textContent = m1AgoLabel(lead.step1_sent_at);
    m1Badge.title = lead.step1_sent_at ? "When Message 1 was marked sent." : "Message 1 has not been marked sent yet.";
    titleEl.appendChild(m1Badge);
    var modalBody = document.getElementById("generic-modal-body");
    modalBody.innerHTML = "";
    [
      { key: "message1", title: "Message 1 — send first (ZERO links)", note: "Personalized inquiry. No URL of any kind." },
      { key: "message2", title: "Message 2 — send ONLY after they reply", note: "Follow-up with the product link." }
    ].forEach(function (item) {
      var section = document.createElement("div");
      section.className = "mb-4";
      var heading = document.createElement("p");
      heading.className = "font-semibold text-sm text-gray-900 dark:text-slate-100";
      heading.textContent = item.title;
      var note = document.createElement("p");
      note.className = "text-xs text-gray-500 dark:text-slate-400 mb-1";
      note.textContent = item.note;
      var text = document.createElement("p");
      text.className = "code-block text-gray-800 dark:text-slate-100";
      text.textContent = lead[item.key] || "—";
      var copy = document.createElement("button");
      copy.type = "button";
      copy.className = "btn btn-secondary btn-sm mt-2";
      copy.textContent = "Copy " + (item.key === "message1" ? "Message 1" : "Message 2");
      copy.disabled = !lead[item.key];
      copy.addEventListener("click", async function () {
        var ok = await window.copyToClipboard(lead[item.key]);
        window.toast(ok ? "Copied." : "Copy failed.", ok ? "success" : "error");
      });
      section.appendChild(heading);
      section.appendChild(note);
      section.appendChild(text);
      section.appendChild(copy);
      modalBody.appendChild(section);
    });
    /* Send-as account override (auto-pick otherwise). */
    var acctSection = document.createElement("div");
    acctSection.className = "mb-4";
    var acctLabel = document.createElement("label");
    acctLabel.className = "field-label";
    acctLabel.textContent = "Send as account";
    var acctSelect = document.createElement("select");
    acctSelect.className = "field-input";
    acctSelect.id = "dm-account-select";
    acctLabel.setAttribute("for", acctSelect.id);
    acctSelect.setAttribute("aria-label", "Send as account");
    var autoOpt = document.createElement("option");
    autoOpt.value = "";
    autoOpt.textContent = "Auto (recommended)";
    acctSelect.appendChild(autoOpt);
    accountsList.forEach(function (account) {
      if (!account.is_active) {
        return;
      }
      var opt = document.createElement("option");
      opt.value = String(account.id);
      opt.textContent = (account.handle ? "@" + account.handle : account.name) +
        " (" + (account.health_status || "healthy") + ")";
      if (lead.assigned_account_id && Number(lead.assigned_account_id) === account.id) {
        opt.selected = true;
      }
      acctSelect.appendChild(opt);
    });
    if (!lead.assigned_account_id) {
      acctSelect.value = "";
    }
    acctSelect.addEventListener("change", function () {
      dmModal.accountId = acctSelect.value ? Number(acctSelect.value) : null;
      refreshDmModalState();
    });
    dmModal.accountId = acctSelect.value ? Number(acctSelect.value) : null;
    acctSection.appendChild(acctLabel);
    acctSection.appendChild(acctSelect);
    modalBody.appendChild(acctSection);
    /* DM Safety: M2 gated send button with live countdown. */
    var safetySection = document.createElement("div");
    safetySection.className = "mb-4 rounded-lg border border-gray-200 dark:border-slate-700 px-4 py-3";
    var safetyHeading = document.createElement("p");
    safetyHeading.className = "font-semibold text-sm text-gray-900 dark:text-slate-100";
    safetyHeading.textContent = "DM Safety — Message 2 gate";
    var safetyNote = document.createElement("p");
    safetyNote.className = "text-xs text-gray-500 dark:text-slate-400 mb-2";
    safetyNote.textContent = "M2 unlocks 5 min after M1 (configurable) and only while hourly/daily quota allows it.";
    var m2Row = document.createElement("div");
    m2Row.className = "flex flex-wrap items-center gap-2";
    var m1Btn = document.createElement("button");
    m1Btn.type = "button";
    m1Btn.className = "btn btn-secondary btn-sm";
    m1Btn.textContent = lead.status === "step1_sent" ? "M1 Sent ✓" : "Mark M1 Sent";
    m1Btn.disabled = lead.status === "step1_sent";
    m1Btn.addEventListener("click", async function () {
      window.setButtonLoading(m1Btn, true, "Marking…");
      try {
        var m1Payload = { status: "step1_sent" };
        if (dmModal.accountId) {
          m1Payload.assigned_account_id = dmModal.accountId;
        }
        var stamped = await window.apiFetch("/api/group-leads/" + lead.id, {
          method: "PATCH",
          body: JSON.stringify(m1Payload)
        });
        lead.status = stamped.status;
        lead.step1_sent_at = stamped.step1_sent_at;
        lead.assigned_account_id = stamped.assigned_account_id;
        m1Btn.textContent = "M1 Sent ✓";
        m1Btn.disabled = true;
        m1Badge.textContent = m1AgoLabel(lead.step1_sent_at);
        window.toast("M1 marked sent. M2 unlocks after the safety gap.", "success");
        loadDmQuota();
        loadLeads();
        refreshDmModalState();
      } catch (err) {
        if (err && err.status === 429) {
          window.toast("Hourly DM limit reached. Wait until " + fmtResetTime(dmQuota.next_reset) + ".", "error");
        } else {
          window.toast(err.message, "error");
        }
      } finally {
        window.setButtonLoading(m1Btn, false);
      }
    });
    var m2Btn = document.createElement("button");
    m2Btn.type = "button";
    m2Btn.className = "btn btn-primary btn-sm";
    m2Btn.textContent = "Send M2 (Locked)";
    m2Btn.disabled = true;
    m2Btn.addEventListener("click", async function () {
      if (m2Btn.disabled) {
        try {
          var preview = await window.apiFetch("/api/group-leads/" + lead.id + "/send-status");
          if (!preview.can_send_m2) {
            if (!preview.rate_limit_ok) {
              window.toast("Hourly DM limit reached. Wait until " + fmtResetTime(dmQuota.next_reset) + ".", "error");
            } else {
              window.toast("Too early — wait " + fmtCountdown(preview.seconds_until_m2) + " before sending M2.", "info");
            }
          }
        } catch (err) {
          window.toast(err.message, "error");
        }
        return;
      }
      window.setButtonLoading(m2Btn, true, "Sending…");
      try {
        var m2Payload = { status: "step2_sent" };
        if (dmModal.accountId) {
          m2Payload.assigned_account_id = dmModal.accountId;
        }
        var sent = await window.apiFetch("/api/group-leads/" + lead.id, {
          method: "PATCH",
          body: JSON.stringify(m2Payload)
        });
        lead.status = sent.status;
        lead.step2_sent_at = sent.step2_sent_at;
        lead.assigned_account_id = sent.assigned_account_id;
        await loadDmQuota();
        window.toast(
          "M2 sent. Counters: " + dmQuota.hourly_used + "/" + dmQuota.hourly_limit + " this hour.",
          "success"
        );
        loadLeads();
        refreshDmModalState();
      } catch (err) {
        if (err && err.status === 409) {
          window.toast("Too early: " + err.message, "info");
        } else if (err && err.status === 429) {
          window.toast("Hourly DM limit reached. Wait until " + fmtResetTime(dmQuota.next_reset) + ".", "error");
        } else {
          window.toast(err.message, "error");
        }
        refreshDmModalState();
      } finally {
        window.setButtonLoading(m2Btn, false);
      }
    });
    m2Row.appendChild(m1Btn);
    m2Row.appendChild(m2Btn);
    var m2Hint = document.createElement("p");
    m2Hint.className = "text-xs text-gray-500 dark:text-slate-400 mt-2";
    m2Hint.textContent = "Checking M2 readiness…";
    safetySection.appendChild(safetyHeading);
    safetySection.appendChild(safetyNote);
    safetySection.appendChild(m2Row);
    safetySection.appendChild(m2Hint);
    modalBody.appendChild(safetySection);
    dmModal.m2Btn = m2Btn;
    dmModal.m2Hint = m2Hint;
    /* Profile link tagging. */
    var profileSection = document.createElement("div");
    profileSection.className = "mb-4";
    var profileHeading = document.createElement("p");
    profileHeading.className = "font-semibold text-sm text-gray-900 dark:text-slate-100";
    profileHeading.textContent = "Facebook profile link (group tagging)";
    var profileNote = document.createElement("p");
    profileNote.className = "text-xs text-gray-500 dark:text-slate-400 mb-1";
    profileNote.textContent = "Used by the 1-click outreach button to open this lead's DM tab.";
    var profileInput = document.createElement("input");
    profileInput.className = "field-input";
    profileInput.placeholder = "https://www.facebook.com/…";
    profileInput.value = lead.user_profile_link || "";
    profileInput.setAttribute("aria-label", "Facebook profile link");
    var profileSave = document.createElement("button");
    profileSave.type = "button";
    profileSave.className = "btn btn-secondary btn-sm mt-2";
    profileSave.textContent = "Save Profile Link";
    profileSave.addEventListener("click", async function () {
      try {
        var updated = await window.apiFetch("/api/group-leads/" + lead.id, {
          method: "PATCH",
          body: JSON.stringify({ user_profile_link: profileInput.value.trim() || null })
        });
        lead.user_profile_link = updated.user_profile_link;
        window.toast("Profile link saved.", "success");
        loadLeads();
      } catch (err) {
        window.toast(err.message, "error");
      }
    });
    profileSection.appendChild(profileHeading);
    profileSection.appendChild(profileNote);
    profileSection.appendChild(profileInput);
    profileSection.appendChild(profileSave);
    modalBody.appendChild(profileSection);
    /* Conversion value logging. */
    var valueSection = document.createElement("div");
    valueSection.className = "mb-1";
    var valueHeading = document.createElement("p");
    valueHeading.className = "font-semibold text-sm text-gray-900 dark:text-slate-100";
    valueHeading.textContent = "Sale value ($ earned from this lead)";
    var valueNote = document.createElement("p");
    valueNote.className = "text-xs text-gray-500 dark:text-slate-400 mb-1";
    valueNote.textContent = "Counts toward Dashboard ROI once the lead is marked Converted.";
    var valueInput = document.createElement("input");
    valueInput.type = "number";
    valueInput.min = "0";
    valueInput.step = "0.01";
    valueInput.className = "field-input";
    valueInput.placeholder = "e.g. 24.99";
    valueInput.value = lead.conversion_value && Number(lead.conversion_value) > 0 ? String(lead.conversion_value) : "";
    valueInput.setAttribute("aria-label", "Conversion value in dollars");
    var valueSave = document.createElement("button");
    valueSave.type = "button";
    valueSave.className = "btn btn-secondary btn-sm mt-2";
    valueSave.textContent = "Save Sale Value";
    valueSave.addEventListener("click", async function () {
      var amount = Number(valueInput.value);
      if (isNaN(amount) || amount < 0) {
        window.toast("Enter a valid amount of 0 or more.", "error");
        return;
      }
      try {
        var saved = await window.apiFetch("/api/group-leads/" + lead.id, {
          method: "PATCH",
          body: JSON.stringify({ conversion_value: amount })
        });
        lead.conversion_value = saved.conversion_value;
        window.toast("Sale value saved: $" + Number(amount).toFixed(2), "success");
        loadLeads();
      } catch (err) {
        window.toast(err.message, "error");
      }
    });
    valueSection.appendChild(valueHeading);
    valueSection.appendChild(valueNote);
    valueSection.appendChild(valueInput);
    valueSection.appendChild(valueSave);
    modalBody.appendChild(valueSection);
    window.openModal("generic-modal");
    refreshDmModalState();
    if (dmModal.timer) {
      clearInterval(dmModal.timer);
    }
    dmModal.timer = setInterval(refreshDmModalState, 30000);
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderCadence();
    renderDmQuota();

    /* DM Safety: quota widget + gap config, refreshed every 60s. */
    loadDmGap();
    loadDmQuota();
    if (dmQuota.timer) {
      clearInterval(dmQuota.timer);
    }
    dmQuota.timer = setInterval(loadDmQuota, 60000);
    var quotaRefresh = document.getElementById("dm-quota-refresh");
    if (quotaRefresh) {
      quotaRefresh.addEventListener("click", loadDmQuota);
    }
    /* Attention Board: bucketed counts, refreshed every 60s (seq-guarded). */
    renderAttention();
    loadAttention();
    if (attention.timer) {
      clearInterval(attention.timer);
    }
    attention.timer = setInterval(function () {
      if (document.visibilityState === "visible") {
        loadAttention();
      }
    }, 60000);
    /* Today's Snapshot: manual numbers + auto funnel, every 120s. */
    loadSnapshot();
    /* Account directory for badges + modal override (refreshed hourly). */
    loadAccountsBrief();
    var accountsTimer = setInterval(function () {
      if (document.visibilityState === "visible") {
        loadAccountsBrief();
      }
    }, 3600000);
    if (snapshot.timer) {
      clearInterval(snapshot.timer);
    }
    snapshot.timer = setInterval(function () {
      if (document.visibilityState === "visible") {
        loadSnapshot();
      }
    }, 120000);
    var snapshotLog = document.getElementById("snapshot-log-btn");
    if (snapshotLog) {
      snapshotLog.addEventListener("click", openLogStatsModal);
    }
    var snapshotEdit = document.getElementById("snapshot-edit-btn");
    if (snapshotEdit) {
      snapshotEdit.addEventListener("click", openLogStatsModal);
    }
    function stopDmPolling() {
      if (dmQuota.timer) {
        clearInterval(dmQuota.timer);
        dmQuota.timer = null;
      }
      if (attention.timer) {
        clearInterval(attention.timer);
        attention.timer = null;
      }
      attention.seq++;
      if (snapshot.timer) {
        clearInterval(snapshot.timer);
        snapshot.timer = null;
      }
      snapshot.seq++;
      if (typeof accountsTimer !== "undefined" && accountsTimer) {
        clearInterval(accountsTimer);
      }
      clearDmModalPoll();
    }
    window.addEventListener("pagehide", stopDmPolling);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        if (dmModal.timer) {
          clearInterval(dmModal.timer);
          dmModal.timer = null;
        }
      } else if (dmModal.leadId && !dmModal.timer) {
        refreshDmModalState();
        dmModal.timer = setInterval(refreshDmModalState, 30000);
      }
    });
    var genericClose = document.getElementById("generic-modal-close");
    if (genericClose) {
      genericClose.addEventListener("click", clearDmModalPoll);
    }
    var genericBackdrop = document.getElementById("generic-modal");
    if (genericBackdrop) {
      genericBackdrop.addEventListener("click", function (event) {
        if (event.target === genericBackdrop) {
          clearDmModalPoll();
        }
      });
    }

    document.getElementById("cadence-roll-btn").addEventListener("click", async function (event) {
      window.setButtonLoading(event.currentTarget, true, "Rolling…");
      try {
        var data = await window.apiFetch("/api/groups/cadence");
        cadence.delay = data.delay_seconds || 0;
        cadence.remaining = 0;
        cadence.finished = false;
        if (cadence.timer) {
          clearInterval(cadence.timer);
          cadence.timer = null;
        }
        renderCadence();
      } catch (err) {
        // Offline fallback: roll locally in the same 180-300s range.
        cadence.delay = 180 + Math.floor(Math.random() * 121);
        cadence.remaining = 0;
        cadence.finished = false;
        renderCadence();
        window.toast("Cadence API unreachable — rolled locally.", "info");
      } finally {
        window.setButtonLoading(event.currentTarget, false);
      }
    });

    document.getElementById("cadence-start-btn").addEventListener("click", function () {
      if (!cadence.delay) {
        window.toast("Roll a safety delay first.", "error");
        return;
      }
      if (cadence.timer) {
        clearInterval(cadence.timer);
      }
      cadence.remaining = cadence.delay;
      cadence.finished = false;
      renderCadence();
      cadence.timer = setInterval(tickCadence, 1000);
    });

    document.getElementById("cadence-reset-btn").addEventListener("click", function () {
      if (cadence.timer) {
        clearInterval(cadence.timer);
        cadence.timer = null;
      }
      cadence.delay = 0;
      cadence.remaining = 0;
      cadence.finished = false;
      renderCadence();
    });

    window
      .apiFetch("/api/products?skip=0&limit=100")
      .then(function (data) {
        ["intent-product", "bulk-product"].forEach(function (selectId) {
          var select = document.getElementById(selectId);
          if (!select) {
            return;
          }
          (data.items || []).forEach(function (product) {
            var opt = document.createElement("option");
            opt.value = String(product.id);
            opt.textContent = product.title;
            select.appendChild(opt);
          });
        });
      })
      .catch(function () {
        /* Product attach is optional. */
      });

    document.getElementById("intent-classify-btn").addEventListener("click", async function (event) {
      var form = intentForm();
      if (!form.comment_text) {
        window.toast("Paste a comment first.", "error");
        return;
      }
      window.setButtonLoading(event.currentTarget, true, "Classifying…");
      try {
        var data = await window.apiFetch("/api/groups/classify", {
          method: "POST",
          body: JSON.stringify({
            comment_text: form.comment_text,
            username: form.username,
            group_name: form.group_name
          })
        });
        renderIntent(data);
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(event.currentTarget, false);
      }
    });

    document.getElementById("intent-save-btn").addEventListener("click", async function (event) {
      var form = intentForm();
      if (!form.comment_text) {
        window.toast("Paste a comment first.", "error");
        return;
      }
      window.setButtonLoading(event.currentTarget, true, "Saving…");
      try {
        var lead = await window.apiFetch("/api/group-leads", {
          method: "POST",
          body: JSON.stringify({
            comment_text: form.comment_text,
            username: form.username,
            group_name: form.group_name,
            product_id: form.product_id
          })
        });
        renderIntent({
          intent: lead.intent,
          confidence: 1,
          signals: [],
          message1: lead.message1,
          message2: lead.message2
        });
        window.toast(
          lead.intent === "high"
            ? "High-intent lead saved with 2-step DMs."
            : "Lead saved as " + lead.intent + " intent (DMs only for high).",
          "success"
        );
        document.getElementById("intent-comment").value = "";
        leadsState.skip = 0;
        loadLeads();
      } catch (err) {
        window.toast(err.message, "error");
      } finally {
        window.setButtonLoading(event.currentTarget, false);
      }
    });

    document.getElementById("leads-filter").addEventListener("change", function (event) {
      leadsState.status = event.target.value;
      if (event.target.value) {
        leadsState.bucket = "";
        try {
          sessionStorage.setItem("groups-bucket", "");
        } catch (err) {
          /* Storage unavailable: ignore. */
        }
        syncBucketChips();
      }
      leadsState.skip = 0;
      loadLeads();
    });
    document.getElementById("leads-refresh-btn").addEventListener("click", loadLeads);

    /* Bucket filter chips + Attention Board tiles (server-side ?bucket=). */
    (function initBucketFilter() {
      var initial = "";
      try {
        var params = new URLSearchParams(window.location.search);
        initial = params.get("bucket") || "";
        if (!initial) {
          initial = sessionStorage.getItem("groups-bucket") || "";
        }
      } catch (err) {
        /* URL/storage unavailable: default to unfiltered. */
      }
      if (["reply_check", "overdue", "m2_waiting", "cold", "unassigned"].indexOf(initial) === -1) {
        initial = "";
      }
      leadsState.bucket = initial;
      Array.prototype.forEach.call(
        document.querySelectorAll("#leads-chips .bucket-chip"),
        function (chip) {
          chip.addEventListener("click", function () {
            if (chip.getAttribute("data-bucket") === "__converted") {
              leadsState.bucket = "";
              leadsState.status = "converted";
              document.getElementById("leads-filter").value = "converted";
              try {
                sessionStorage.setItem("groups-bucket", "");
              } catch (err) {
                /* Ignore. */
              }
              leadsState.skip = 0;
              syncBucketChips();
              loadLeads();
              return;
            }
            leadsState.status = "";
            document.getElementById("leads-filter").value = "";
            setBucket(chip.getAttribute("data-bucket"));
          });
        }
      );
      Array.prototype.forEach.call(
        document.querySelectorAll("#attention-board .attention-tile"),
        function (tile) {
          tile.addEventListener("click", function () {
            leadsState.status = "";
            document.getElementById("leads-filter").value = "";
            setBucket(tile.getAttribute("data-bucket"));
          });
        }
      );
      syncBucketChips();
    })();

    /* Bulk selection: header select-all + Mark Selected as Replied (cap 100). */
    var selectAllBox = document.getElementById("leads-select-all");
    if (selectAllBox) {
      selectAllBox.addEventListener("change", function (event) {
        var boxes = document.querySelectorAll("#leads-body .lead-select");
        Array.prototype.forEach.call(boxes, function (box) {
          box.checked = event.target.checked;
          var id = Number(box.value);
          if (event.target.checked) {
            selectedLeads[id] = true;
          } else {
            delete selectedLeads[id];
          }
        });
        updateBulkBar();
      });
    }
    var bulkClear = document.getElementById("leads-bulk-clear");
    if (bulkClear) {
      bulkClear.addEventListener("click", function () {
        selectedLeads = {};
        updateBulkBar();
        loadLeads();
      });
    }
    var bulkAssign = document.getElementById("leads-bulk-assign");
    if (bulkAssign) {
      bulkAssign.addEventListener("click", async function (event) {
        var ids = Object.keys(selectedLeads).map(Number).slice(0, 500);
        if (ids.length === 0) {
          window.toast("Select at least one lead first.", "error");
          return;
        }
        window.setButtonLoading(event.currentTarget, true, "Assigning…");
        try {
          var result = await window.apiFetch("/api/accounts/auto-assign-orphans", {
            method: "POST",
            body: JSON.stringify({ ids: ids })
          });
          selectedLeads = {};
          window.toast(
            "Auto-assigned " + result.assigned + " lead(s)." +
            (result.skipped ? " Skipped " + result.skipped + "." : ""),
            "success"
          );
          loadLeads();
          loadAttention();
        } catch (err) {
          window.toast(err.message, "error");
        } finally {
          window.setButtonLoading(event.currentTarget, false);
        }
      });
    }
    var bulkReplied = document.getElementById("leads-bulk-replied");
    if (bulkReplied) {
      bulkReplied.addEventListener("click", async function (event) {
        var ids = Object.keys(selectedLeads).map(Number).slice(0, 100);
        if (ids.length === 0) {
          window.toast("Select at least one lead first.", "error");
          return;
        }
        window.setButtonLoading(event.currentTarget, true, "Marking…");
        try {
          var result = await window.apiFetch("/api/group-leads/bulk-mark-reply", {
            method: "POST",
            body: JSON.stringify({ ids: ids, reply_state: "replied" })
          });
          selectedLeads = {};
          window.toast(
            "Marked " + result.updated.length + " lead(s) as replied." +
            (result.skipped && result.skipped.length ? " Skipped " + result.skipped.length + "." : ""),
            "success"
          );
          loadLeads();
          loadAttention();
        } catch (err) {
          window.toast(err.message, "error");
        } finally {
          window.setButtonLoading(event.currentTarget, false);
        }
      });
    }

    var bulkBtn = document.getElementById("bulk-parse-btn");
    if (bulkBtn) {
      bulkBtn.addEventListener("click", async function (event) {
        var text = document.getElementById("bulk-comments").value.trim();
        if (!text) {
          window.toast("Paste at least one comment first.", "error");
          return;
        }
        var groupTag = document.getElementById("bulk-group").value.trim() || null;
        var bulkProduct = document.getElementById("bulk-product").value
          ? Number(document.getElementById("bulk-product").value)
          : null;
        window.setButtonLoading(event.currentTarget, true, "Parsing…");
        try {
          var result = await window.apiFetch("/api/groups/leads/bulk-parse", {
            method: "POST",
            body: JSON.stringify({ text: text, group_name: groupTag, product_id: bulkProduct })
          });
          var box = document.getElementById("bulk-result");
          box.classList.remove("hidden");
          box.innerHTML = "";
          var summary = document.createElement("p");
          summary.className = "font-semibold text-gray-900 dark:text-slate-100";
          summary.textContent =
            "Parsed " + result.total_parsed + " · saved " + result.saved_high + " high-intent lead(s).";
          box.appendChild(summary);
          if (result.skipped && result.skipped.length) {
            var skipped = document.createElement("p");
            skipped.className = "mt-2 text-xs text-gray-500 dark:text-slate-400";
            skipped.textContent =
              "Skipped (" + result.skipped.length + "): " +
              result.skipped.slice(0, 10).map(function (s) {
                return "@" + s.username + " [" + s.intent + "]";
              }).join(", ") +
              (result.skipped.length > 10 ? " …" : "");
            box.appendChild(skipped);
          }
          window.toast("Saved " + result.saved_high + " high-intent lead(s).", "success");
          document.getElementById("bulk-comments").value = "";
          leadsState.skip = 0;
          loadLeads();
        } catch (err) {
          window.toast(err.message, "error");
        } finally {
          window.setButtonLoading(event.currentTarget, false);
        }
      });
    }

    loadLeads();
  });
})();
