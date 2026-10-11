/* Dashboard page: stats, status bars, activity, quick generate. */
(function () {
  "use strict";

  var REFRESH_MS = 60000;
  var TODAY_ACTIONS_MS = 90000;
  var todayActions = { timer: null, seq: 0 };
  var healthStats = { chartTimer: null, digestTimer: null, tplTimer: null, seq: 0 };
  var SVG_NS = "http://www.w3.org/2000/svg";

  /**
   * Load the Today's Actions card from bucketed attention counts.
   * Request-seq guarded so slow responses never overwrite fresher ones.
   */
  async function loadTodayActions() {
    var card = document.getElementById("today-actions-list");
    if (!card) {
      return;
    }
    var mySeq = ++todayActions.seq;
    try {
      var data = await window.apiFetch("/api/group-leads/attention");
      if (mySeq !== todayActions.seq) {
        return;
      }
      var counts = data.counts || {};
      var reply = Number(counts.reply_check) || 0;
      var overdue = Number(counts.overdue) || 0;
      var m2 = Number(counts.m2_waiting) || 0;
      var cold = Number(counts.cold_followup_ready) || 0;
      document.getElementById("today-actions-reply").textContent = String(reply);
      var overdueEl = document.getElementById("today-actions-overdue");
      overdueEl.textContent = String(overdue);
      overdueEl.className = overdue > 0 ? "text-red-600 dark:text-red-400" : "";
      document.getElementById("today-actions-m2").textContent = String(m2);
      document.getElementById("today-actions-cold").textContent = String(cold);
      var allZero = reply === 0 && overdue === 0 && m2 === 0 && cold === 0;
      document.getElementById("today-actions-caught-up").classList.toggle("hidden", !allZero);
      card.classList.toggle("hidden", allZero);
    } catch (err) {
      /* Best-effort widget: keep previous values, warn for diagnostics. */
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Today's Actions unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render stat cards, status bars and activity from stats payload.
   * @param {Object} stats - Dashboard stats payload.
   */
  function renderStats(stats) {
    document.getElementById("stat-products").textContent = String(stats.total_products);
    document.getElementById("stat-products-active").textContent = String(stats.active_products);
    document.getElementById("stat-posts").textContent = String(stats.total_posts);
    document.getElementById("stat-scheduled").textContent = String(stats.posts_scheduled_next_24h);
    document.getElementById("stat-published").textContent = String(
      stats.posts_published_last_7_days
    );
    document.getElementById("stat-ai").textContent = String(stats.ai_generations_total);
    document.getElementById("stat-ai-failed").textContent = String(stats.ai_generations_failed);

    var bars = document.getElementById("status-bars");
    var empty = document.getElementById("status-bars-empty");
    bars.innerHTML = "";
    var byStatus = stats.posts_by_status || {};
    var order = ["draft", "scheduled", "published", "failed"];
    var colors = {
      draft: "background-color:#9ca3af",
      scheduled: "background-color:#3b82f6",
      published: "background-color:#22c55e",
      failed: "background-color:#ef4444"
    };
    var max = 0;
    order.forEach(function (key) {
      max = Math.max(max, byStatus[key] || 0);
    });
    if (max === 0) {
      empty.classList.remove("hidden");
    } else {
      empty.classList.add("hidden");
      order.forEach(function (key) {
        var count = byStatus[key] || 0;
        var row = document.createElement("div");
        var head = document.createElement("div");
        head.className = "flex justify-between text-sm mb-1";
        var name = document.createElement("span");
        name.className = "font-medium capitalize text-gray-900 dark:text-slate-100";
        name.textContent = key;
        var value = document.createElement("span");
        value.className = "text-gray-500 dark:text-slate-400";
        value.textContent = String(count);
        head.appendChild(name);
        head.appendChild(value);
        var track = document.createElement("div");
        track.className = "stat-bar";
        var fill = document.createElement("div");
        fill.className = "stat-bar-fill";
        fill.style.cssText = colors[key] + ";width:" + Math.round((count / max) * 100) + "%";
        track.appendChild(fill);
        row.appendChild(head);
        row.appendChild(track);
        bars.appendChild(row);
      });
    }

    var list = document.getElementById("activity-list");
    var activityEmpty = document.getElementById("activity-empty");
    list.innerHTML = "";
    var activity = stats.recent_activity || [];
    if (activity.length === 0) {
      activityEmpty.classList.remove("hidden");
    } else {
      activityEmpty.classList.add("hidden");
      activity.forEach(function (entry) {
        var item = document.createElement("li");
        item.className = "py-3 flex items-start gap-3";
        var badge = document.createElement("span");
        badge.innerHTML = window.statusBadge(entry.level);
        var body = document.createElement("div");
        body.className = "min-w-0 flex-1";
        var msg = document.createElement("p");
        msg.className = "text-sm text-gray-900 dark:text-slate-100";
        msg.textContent = entry.message;
        var meta = document.createElement("p");
        meta.className = "text-xs text-gray-400 dark:text-slate-500 mt-1";
        meta.textContent = entry.event_type + " \u00b7 " + window.timeAgo(entry.created_at);
        body.appendChild(msg);
        body.appendChild(meta);
        item.appendChild(badge);
        item.appendChild(body);
        list.appendChild(item);
      });
    }
  }

  /**
   * Load health info into the system status card.
   */
  async function loadHealth() {
    try {
      var data = await window.apiFetch("/api/health");
      document.getElementById("stat-health").textContent = data.status;
      document.getElementById("stat-health-sub").textContent =
        data.environment + " \u00b7 " + data.ai_provider;
    } catch (err) {
      document.getElementById("stat-health").textContent = "down";
      document.getElementById("stat-health-sub").textContent = err.message;
    }
  }

  /**
   * Load Automation status and the Facebook configuration banner.
   */
  async function loadAutomation() {
    try {
      var data = await window.apiFetch("/api/automation/status");
      document.getElementById("stat-automation").textContent = data.running
        ? "running"
        : "paused";
      var result = data.last_run_result || {};
      var summary = "no runs yet";
      if (data.last_run_at) {
        summary =
          "published " + (result.published || 0) + ", failed " + (result.failed || 0);
      }
      document.getElementById("stat-automation-sub").textContent = summary;
    } catch (err) {
      document.getElementById("stat-automation").textContent = "unknown";
      document.getElementById("stat-automation-sub").textContent = err.message;
    }
    try {
      var fb = await window.apiFetch("/api/facebook/status");
      var show = !fb.configured && !fb.dry_run;
      document.getElementById("fb-not-configured").classList.toggle("hidden", !show);
    } catch (err) {
      document.getElementById("fb-not-configured").classList.add("hidden");
    }
  }

  /**
   * Load products into the quick-generate dropdown.
   */
  async function loadProducts() {
    var select = document.getElementById("quick-product");
    select.innerHTML = "";
    var data = await window.apiFetch("/api/products?skip=0&limit=100");
    if (data.items.length === 0) {
      var opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No products yet \u2014 add one first";
      select.appendChild(opt);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    data.items.forEach(function (product) {
      var opt = document.createElement("option");
      opt.value = String(product.id);
      opt.textContent = product.title;
      select.appendChild(opt);
    });
  }

  /**
   * Load Group DM revenue stats and the converted-lead dropdown.
   */
  async function loadRevenue() {
    var totalEl = document.getElementById("revenue-total");
    if (!totalEl) {
      return;
    }
    function money(value) {
      return "$" + Number(value || 0).toFixed(2);
    }
    try {
      var stats = await window.apiFetch("/api/groups/revenue");
      totalEl.textContent = money(stats.total_revenue);
      document.getElementById("revenue-count").textContent = String(stats.converted_count || 0);
      document.getElementById("revenue-avg").textContent = money(stats.average_value);
    } catch (err) {
      totalEl.textContent = "—";
    }
    var select = document.getElementById("revenue-lead");
    var empty = document.getElementById("revenue-empty");
    try {
      var data = await window.apiFetch("/api/group-leads?skip=0&limit=100&status=converted");
      select.innerHTML = "";
      if (!data.items || data.items.length === 0) {
        var opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No converted leads yet";
        select.appendChild(opt);
        select.disabled = true;
        empty.classList.remove("hidden");
        return;
      }
      select.disabled = false;
      empty.classList.add("hidden");
      data.items.forEach(function (lead) {
        var opt = document.createElement("option");
        opt.value = String(lead.id);
        var current = lead.conversion_value && Number(lead.conversion_value) > 0
          ? " — $" + Number(lead.conversion_value).toFixed(2)
          : "";
        opt.textContent = "@" + lead.username + current;
        select.appendChild(opt);
      });
    } catch (err) {
      /* Revenue dropdown is best-effort. */
    }
  }

  /**
   * Handle the revenue log form submission.
   * @param {Event} event - Submit event.
   */
  async function onRevenueLog(event) {
    event.preventDefault();
    var btn = document.getElementById("revenue-save-btn");
    var leadId = document.getElementById("revenue-lead").value;
    var amount = Number(document.getElementById("revenue-amount").value);
    if (!leadId) {
      window.toast("No converted lead to log.", "error");
      return;
    }
    if (isNaN(amount) || amount < 0) {
      window.toast("Enter a valid amount of 0 or more.", "error");
      return;
    }
    window.setButtonLoading(btn, true, "Logging…");
    try {
      await window.apiFetch("/api/group-leads/" + leadId, {
        method: "PATCH",
        body: JSON.stringify({ conversion_value: amount })
      });
      window.toast("Sale logged: $" + amount.toFixed(2), "success");
      document.getElementById("revenue-amount").value = "";
      loadRevenue();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Load the growth chart, weekly digest, and template performance cards.
   * Each fetch is request-seq guarded so stale responses never win.
   */
  async function loadGrowthChart() {
    var wrap = document.getElementById("growth-chart");
    if (!wrap) {
      return;
    }
    var mySeq = ++healthStats.seq;
    try {
      var data = await window.apiFetch("/api/stats/daily");
      if (mySeq !== healthStats.seq) {
        return;
      }
      renderGrowthChart(data.items || []);
      var range = document.getElementById("growth-chart-range");
      if (range && data.start && data.end) {
        range.textContent = data.start + " → " + data.end;
      }
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Growth chart unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render an inline SVG two-line chart (members blue, leads green).
   * Guards: empty → empty state; single point → dots; zero max → flat.
   * @param {Array} items - Ascending daily stat rows.
   */
  function renderGrowthChart(items) {
    var wrap = document.getElementById("growth-chart");
    var empty = document.getElementById("growth-chart-empty");
    wrap.innerHTML = "";
    var hasData = (items || []).some(function (row) {
      return (Number(row.member_count) || 0) > 0 || (Number(row.leads_captured) || 0) > 0;
    });
    if (!hasData) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    var width = 600;
    var height = 220;
    var padL = 44;
    var padB = 28;
    var padT = 12;
    var innerW = width - padL - 8;
    var innerH = height - padT - padB;
    var max = 1;
    items.forEach(function (row) {
      max = Math.max(max, Number(row.member_count) || 0, Number(row.leads_captured) || 0);
    });
    function xPos(i) {
      if (items.length === 1) {
        return padL + innerW / 2;
      }
      return padL + (i / (items.length - 1)) * innerW;
    }
    function yPos(value) {
      return padT + innerH - (Number(value) / max) * innerH;
    }
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("class", "w-full h-auto");
    svg.setAttribute("role", "img");
    // Gridlines + Y labels (0, mid, max).
    [0, max / 2, max].forEach(function (tick) {
      var y = yPos(tick);
      var line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", padL);
      line.setAttribute("x2", width - 8);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "currentColor");
      line.setAttribute("class", "text-gray-200 dark:text-slate-700");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);
      var label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", padL - 6);
      label.setAttribute("y", y + 4);
      label.setAttribute("text-anchor", "end");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "currentColor");
      label.setAttribute("class", "text-gray-500 dark:text-slate-400");
      label.textContent = String(Math.round(tick));
      svg.appendChild(label);
    });
    // X labels: every 5th date (always the last).
    items.forEach(function (row, i) {
      if (i % 5 !== 0 && i !== items.length - 1) {
        return;
      }
      var label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", xPos(i));
      label.setAttribute("y", height - 8);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "currentColor");
      label.setAttribute("class", "text-gray-500 dark:text-slate-400");
      label.textContent = String(row.stat_date).slice(5);
      svg.appendChild(label);
    });
    // Series lines + hoverable dots (native <title> tooltips).
    [
      { key: "member_count", color: "#3b82f6", label: "Members" },
      { key: "leads_captured", color: "#22c55e", label: "Leads" }
    ].forEach(function (series) {
      var points = items.map(function (row, i) {
        return xPos(i).toFixed(1) + "," + yPos(row[series.key]).toFixed(1);
      }).join(" ");
      var line = document.createElementNS(SVG_NS, "polyline");
      line.setAttribute("points", points);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", series.color);
      line.setAttribute("stroke-width", "2");
      svg.appendChild(line);
      items.forEach(function (row, i) {
        var dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("cx", xPos(i));
        dot.setAttribute("cy", yPos(row[series.key]));
        dot.setAttribute("r", "3.5");
        dot.setAttribute("fill", series.color);
        var tip = document.createElementNS(SVG_NS, "title");
        tip.textContent = row.stat_date + " — " + series.label + ": " + row[series.key];
        dot.appendChild(tip);
        svg.appendChild(dot);
      });
    });
    wrap.appendChild(svg);
  }

  /**
   * Load the weekly digest card (this week vs last week + deltas).
   */
  async function loadWeeklyDigest() {
    var wrap = document.getElementById("weekly-digest");
    if (!wrap) {
      return;
    }
    var mySeq = ++healthStats.seq;
    try {
      var data = await window.apiFetch("/api/stats/weekly-digest");
      if (mySeq !== healthStats.seq) {
        return;
      }
      renderWeeklyDigest(data);
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Weekly digest unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render digest rows with green/red/gray delta arrows.
   * @param {Object} data - Digest payload.
   */
  function renderWeeklyDigest(data) {
    var wrap = document.getElementById("weekly-digest");
    var empty = document.getElementById("weekly-digest-empty");
    wrap.innerHTML = "";
    var rows = [
      { key: "member_count", label: "Members", money: false, absolute: true },
      { key: "new_members", label: "New", money: false },
      { key: "posts_published", label: "Posts", money: false },
      { key: "comments_received", label: "Comments", money: false },
      { key: "leads_captured", label: "Leads", money: false },
      { key: "m1_sent", label: "M1", money: false },
      { key: "m2_sent", label: "M2", money: false },
      { key: "converted", label: "Converted", money: false },
      { key: "revenue", label: "Revenue", money: true }
    ];
    function fmt(value, money) {
      if (money) {
        return "$" + Number(value || 0).toFixed(2);
      }
      return String(value === null || value === undefined ? 0 : value);
    }
    var anyData = rows.some(function (row) {
      return Number((data.this_week || {})[row.key]) > 0 ||
        Number((data.last_week || {})[row.key]) > 0;
    });
    if (!anyData) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    var head = document.createElement("div");
    head.className = "grid grid-cols-4 gap-2 text-xs font-semibold text-gray-500 dark:text-slate-400 pb-1 border-b border-gray-200 dark:border-slate-700";
    ["", "This wk", "Last wk", "Δ"].forEach(function (text) {
      var cell = document.createElement("span");
      cell.textContent = text;
      head.appendChild(cell);
    });
    wrap.appendChild(head);
    rows.forEach(function (row) {
      var line = document.createElement("div");
      line.className = "grid grid-cols-4 gap-2 py-1 border-b border-gray-100 dark:border-slate-800";
      var name = document.createElement("span");
      name.className = "text-gray-600 dark:text-slate-300";
      name.textContent = row.label;
      var thisEl = document.createElement("span");
      thisEl.className = "font-semibold text-gray-900 dark:text-slate-100";
      thisEl.textContent = fmt(data.this_week[row.key], row.money);
      var lastEl = document.createElement("span");
      lastEl.className = "text-gray-500 dark:text-slate-400";
      lastEl.textContent = fmt(data.last_week[row.key], row.money);
      var deltaEl = document.createElement("span");
      var trend = (data.trend || {})[row.key];
      var delta = (data.delta || {})[row.key];
      if (delta === null || delta === undefined) {
        deltaEl.textContent = Number(data.this_week[row.key]) > 0 ? "▲ new" : "—";
        deltaEl.className = Number(data.this_week[row.key]) > 0
          ? "text-green-600 dark:text-green-400"
          : "text-gray-400 dark:text-slate-500";
      } else {
        var arrow = trend === "up" ? "▲ " : trend === "down" ? "▼ " : "";
        deltaEl.textContent = row.absolute
          ? arrow + (delta > 0 ? "+" : "") + delta
          : arrow + delta + "%";
        deltaEl.className = trend === "up"
          ? "text-green-600 dark:text-green-400"
          : trend === "down"
            ? "text-red-600 dark:text-red-400"
            : "text-gray-400 dark:text-slate-500";
      }
      line.appendChild(name);
      line.appendChild(thisEl);
      line.appendChild(lastEl);
      line.appendChild(deltaEl);
      wrap.appendChild(line);
    });
  }

  /**
   * Load the template performance table (server-sorted by revenue).
   */
  async function loadTemplatePerf() {
    var body = document.getElementById("template-perf-body");
    if (!body) {
      return;
    }
    var mySeq = ++healthStats.seq;
    try {
      var data = await window.apiFetch("/api/stats/templates?days=30");
      if (mySeq !== healthStats.seq) {
        return;
      }
      renderTemplatePerf(data.items || []);
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Template performance unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render template rows; top 3 get a subtle highlight.
   * @param {Array} items - Template rollups, revenue DESC.
   */
  function renderTemplatePerf(items) {
    var body = document.getElementById("template-perf-body");
    var empty = document.getElementById("template-perf-empty");
    body.innerHTML = "";
    if (!items.length) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    items.forEach(function (row, index) {
      var tr = document.createElement("tr");
      tr.className = "border-b border-gray-100 dark:border-slate-700" +
        (index < 3 ? " bg-amber-50/60 dark:bg-amber-900/20 font-medium" : "");
      var name = document.createElement("td");
      name.className = "py-2 pr-3 text-gray-900 dark:text-slate-100";
      name.textContent = row.template_name || "unknown";
      var posted = document.createElement("td");
      posted.className = "py-2 pr-3 text-gray-600 dark:text-slate-300";
      posted.textContent = String(row.posts_posted);
      var leads = document.createElement("td");
      leads.className = "py-2 pr-3 text-gray-600 dark:text-slate-300";
      leads.textContent = String(row.leads_captured);
      var conv = document.createElement("td");
      conv.className = "py-2 pr-3 text-gray-600 dark:text-slate-300";
      conv.textContent = String(row.converted);
      var rate = document.createElement("td");
      rate.className = "py-2 pr-3 text-gray-600 dark:text-slate-300";
      rate.textContent = (Number(row.conversion_rate || 0) * 100).toFixed(1) + "%";
      var revenue = document.createElement("td");
      revenue.className = "py-2 font-semibold text-gray-900 dark:text-slate-100";
      revenue.textContent = "$" + Number(row.revenue || 0).toFixed(2);
      [name, posted, leads, conv, rate, revenue].forEach(function (cell) {
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
  }
  /**
   * Load the System Health card + token banner (request-seq guarded).
   */
  async function loadSystemHealth() {
    var wrap = document.getElementById("health-pills");
    if (!wrap) {
      return;
    }
    var mySeq = ++sysHealth.seq;
    try {
      var data = await window.apiFetch("/api/system/health");
      if (mySeq !== sysHealth.seq) {
        return;
      }
      renderHealthPills(data);
      renderTokenBanner(data);
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("System health unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render the 6 health pills; the kill-switch pill toggles on click.
   * @param {Object} data - Health payload.
   */
  function renderHealthPills(data) {
    var wrap = document.getElementById("health-pills");
    wrap.innerHTML = "";
    function pill(label, ok, sub, warn) {
      var el = document.createElement("span");
      el.className = "badge " + (ok ? "badge-green" : warn ? "badge-amber" : "badge-red");
      var dot = document.createElement("span");
      dot.className = "badge-dot";
      dot.setAttribute("aria-hidden", "true");
      var text = document.createElement("span");
      text.textContent = label + ": " + sub;
      el.appendChild(dot);
      el.appendChild(text);
      el.title = label + " — " + sub;
      return el;
    }
    var db = data.db || {};
    var fb = data.fb || {};
    var ai = data.ai || {};
    var queue = data.queue || {};
    var backup = data.backup || {};
    wrap.appendChild(pill("DB", !!db.ok, db.ok ? (db.size_mb + " MB") : "down"));
    wrap.appendChild(pill("FB API", !!fb.ok, fb.ok ? (fb.page_name || "connected") : "check"));
    wrap.appendChild(pill("AI", !!ai.ok, ai.primary_provider || "unknown"));
    var queueSub = "posts " + (queue.pending_posts || 0) + " · leads " + (queue.pending_leads || 0);
    wrap.appendChild(pill("Queue", !!queue.ok, queueSub));
    wrap.appendChild(pill(
      "Backup",
      !!backup.ok,
      backup.last_backup_at ? ("age " + backup.age_hours + "h") : "none yet",
      !backup.ok && !!backup.last_backup_at
    ));
    var accts = data.accounts || {};
    if (accts.total !== undefined) {
      var acctOk = (accts.active || 0) > 0 && (accts.banned || 0) < (accts.total || 0);
      var acctWarn = !acctOk || (accts.warned || 0) > 0;
      wrap.appendChild(pill(
        "Accounts",
        acctOk && !acctWarn,
        (accts.active || 0) + "/" + (accts.total || 0) + " active",
        acctWarn
      ));
    }
    var killOn = !!data.kill_switch;
    var kill = document.createElement("button");
    kill.type = "button";
    kill.className = "badge " + (killOn ? "badge-red" : "badge-green");
    kill.title = killOn ? "Emergency stop is ACTIVE — click to release" : "Emergency stop is off — click to engage";
    var killDot = document.createElement("span");
    killDot.className = "badge-dot";
    killDot.setAttribute("aria-hidden", "true");
    var killText = document.createElement("span");
    killText.textContent = killOn ? "🛑 ACTIVE" : "✅ OFF";
    kill.appendChild(killDot);
    kill.appendChild(killText);
    kill.addEventListener("click", async function () {
      if (!killOn) {
        var confirmed = await window.confirmDialog(
          "Engage the emergency stop? ALL publishing halts immediately.",
          { confirmText: "Engage Kill Switch", danger: true }
        );
        if (!confirmed) {
          return;
        }
      }
      try {
        var result = await window.apiFetch("/api/system/kill-switch", {
          method: "POST",
          headers: killOn ? {} : { "X-Confirm-Delete": "true" },
          body: JSON.stringify({ active: !killOn })
        });
        window.toast(
          result.kill_switch_active ? "Emergency stop ENGAGED." : "Emergency stop released.",
          result.kill_switch_active ? "error" : "success"
        );
        loadSystemHealth();
      } catch (err) {
        window.toast(err.message, "error");
      }
    });
    var killWrap = document.createElement("span");
    killWrap.textContent = "Kill Switch ";
    killWrap.className = "text-sm text-gray-600 dark:text-slate-300";
    killWrap.appendChild(kill);
    wrap.appendChild(killWrap);
  }

  /**
   * Show the token banner only when 30 or fewer days remain.
   * @param {Object} data - Health payload (fb.token_days_left).
   */
  function renderTokenBanner(data) {
    var banner = document.getElementById("token-warning-banner");
    if (!banner) {
      return;
    }
    var days = data.fb ? data.fb.token_days_left : null;
    if (days === null || days === undefined || days > 30) {
      banner.classList.add("hidden");
      return;
    }
    banner.classList.remove("hidden");
    var base = "mb-4 text-sm font-medium rounded-lg px-4 py-3 ";
    if (days <= 0) {
      banner.className = base + "text-red-800 dark:text-red-200 bg-red-50/80 dark:bg-red-900/30 border border-red-200 dark:border-red-800";
      banner.textContent = "Your Facebook token has expired. Publishing will fail — refresh it in Settings → System & Backups.";
    } else if (days < 7) {
      banner.className = base + "text-red-800 dark:text-red-200 bg-red-50/80 dark:bg-red-900/30 border border-red-200 dark:border-red-800";
      banner.textContent = "Your Facebook token expires in " + days + " day(s). Refresh now in Settings.";
    } else if (days <= 14) {
      banner.className = base + "text-amber-800 dark:text-amber-200 bg-amber-50/80 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800";
      banner.textContent = "Your Facebook token expires in " + days + " days. Plan a refresh soon.";
    } else {
      banner.className = base + "text-amber-800 dark:text-amber-200 bg-amber-50/80 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800";
      banner.textContent = "Your Facebook token expires in " + days + " days.";
    }
  }

  /**
   * Load the AI usage mini-widget with a cost sparkline.
   */
  async function loadAiWidget() {
    var spark = document.getElementById("ai-usage-spark");
    if (!spark) {
      return;
    }
    var mySeq = ++sysHealth.seq;
    try {
      var data = await window.apiFetch("/api/system/ai-usage?days=30");
      if (mySeq !== sysHealth.seq) {
        return;
      }
      var mtd = data.month_to_date || {};
      document.getElementById("ai-usage-mtd").textContent =
        (mtd.calls || 0) + " calls · $" + Number(mtd.cost_usd || 0).toFixed(4) + " this month";
      renderCostSpark(data.by_day || []);
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("AI usage widget unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render a 30-point daily-cost sparkline (inline SVG, crash-safe).
   * @param {Array} days - [{date, cost_usd}] ascending.
   */
  function renderCostSpark(days) {
    var spark = document.getElementById("ai-usage-spark");
    var empty = document.getElementById("ai-usage-empty");
    spark.innerHTML = "";
    var hasData = (days || []).some(function (d) {
      return Number(d.cost_usd) > 0 || Number(d.calls) > 0;
    });
    if (!hasData) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    var width = 300;
    var height = 48;
    var max = 0;
    days.forEach(function (d) {
      max = Math.max(max, Number(d.cost_usd) || 0);
    });
    if (max <= 0) {
      max = 1;
    }
    function xPos(i) {
      if (days.length === 1) {
        return width / 2;
      }
      return (i / (days.length - 1)) * width;
    }
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("class", "w-full h-auto");
    svg.setAttribute("role", "img");
    var points = days.map(function (d, i) {
      var y = height - 4 - (Number(d.cost_usd) / max) * (height - 8);
      return xPos(i).toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    var line = document.createElementNS(SVG_NS, "polyline");
    line.setAttribute("points", points);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "#8b5cf6");
    line.setAttribute("stroke-width", "2");
    svg.appendChild(line);
    days.forEach(function (d, i) {
      var y = height - 4 - (Number(d.cost_usd) / max) * (height - 8);
      var dot = document.createElementNS(SVG_NS, "circle");
      dot.setAttribute("cx", xPos(i));
      dot.setAttribute("cy", y);
      dot.setAttribute("r", "3");
      dot.setAttribute("fill", "#8b5cf6");
      var tip = document.createElementNS(SVG_NS, "title");
      tip.textContent = d.date + " — $" + Number(d.cost_usd).toFixed(4) + " (" + d.calls + " calls)";
      dot.appendChild(tip);
      svg.appendChild(dot);
    });
    spark.appendChild(svg);
  }
  /**
   * Load the Accounts Overview card (request-seq guarded).
   */
  async function loadAccountsOverview() {
    var wrap = document.getElementById("accounts-overview");
    if (!wrap) {
      return;
    }
    var mySeq = ++sysHealth.seq;
    try {
      var data = await window.apiFetch("/api/accounts?include_inactive=false");
      if (mySeq !== sysHealth.seq) {
        return;
      }
      renderAccountsOverview(data.items || []);
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("Accounts overview unavailable:", err && err.message);
      }
    }
  }

  /**
   * Render one row per active account with mini usage bars.
   * @param {Array} items - Account payloads.
   */
  function renderAccountsOverview(items) {
    var wrap = document.getElementById("accounts-overview");
    var empty = document.getElementById("accounts-overview-empty");
    wrap.innerHTML = "";
    if (!items.length) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    items.forEach(function (account) {
      var row = document.createElement("a");
      row.href = "/accounts#" + account.id;
      row.className = "block rounded-lg border border-gray-200 dark:border-slate-700 px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-800/50";
      var head = document.createElement("div");
      head.className = "flex items-center gap-2";
      var name = document.createElement("span");
      name.className = "font-medium text-gray-900 dark:text-slate-100";
      name.textContent = account.persona_name || account.name;
      var health = document.createElement("span");
      var status = account.health_status || "healthy";
      health.className = "badge " + (status === "healthy" ? "badge-green" : status === "warned" ? "badge-amber" : "badge-red");
      health.textContent = status;
      var rate = document.createElement("span");
      rate.className = "ml-auto text-xs text-gray-500 dark:text-slate-400";
      rate.textContent = (Number(account.d30_rate || 0) * 100).toFixed(1) + "% conv (30d)";
      head.appendChild(name);
      head.appendChild(health);
      head.appendChild(rate);
      row.appendChild(head);
      [["h", account.hourly_used, account.hourly_limit],
       ["d", account.daily_used, account.daily_limit]].forEach(function (bar, index) {
        var track = document.createElement("div");
        track.className = "stat-bar mt-1";
        track.title = (index === 0 ? "Hourly " : "Daily ") + bar[1] + "/" + bar[2];
        var fill = document.createElement("div");
        var ratio = bar[2] > 0 ? bar[1] / bar[2] : 0;
        fill.className = "stat-bar-fill " + (ratio >= 0.9 ? "bg-red-500" : ratio >= 0.6 ? "bg-amber-500" : "bg-green-500");
        fill.style.width = Math.min(100, Math.round(ratio * 100)) + "%";
        track.appendChild(fill);
        row.appendChild(track);
      });
      wrap.appendChild(row);
    });
  }
  async function loadDashboard() {
    var loading = document.getElementById("dashboard-loading");
    var content = document.getElementById("dashboard-content");
    var errorBox = document.getElementById("dashboard-error");
    var errorText = document.getElementById("dashboard-error-text");
    try {
      var stats = await window.apiFetch("/api/dashboard/stats");
      renderStats(stats);
      errorBox.classList.add("hidden");
      loading.classList.add("hidden");
      content.classList.remove("hidden");
    } catch (err) {
      errorText.textContent = "Could not load dashboard data: " + err.message;
      errorBox.classList.remove("hidden");
      loading.classList.add("hidden");
    }
    loadHealth();
  }

  /**
   * Handle the quick-generate form submission.
   * @param {Event} event - Submit event.
   */
  async function onQuickGenerate(event) {
    event.preventDefault();
    var btn = document.getElementById("quick-generate-btn");
    var result = document.getElementById("quick-generate-result");
    var productId = document.getElementById("quick-product").value;
    var tone = document.getElementById("quick-tone").value;
    if (!productId) {
      window.toast("Add a product before generating.", "error");
      return;
    }
    window.setButtonLoading(btn, true, "Generating\u2026");
    try {
      var post = await window.apiFetch("/api/ai/generate", {
        method: "POST",
        body: JSON.stringify({ product_id: Number(productId), tone: tone })
      });
      window.toast("Draft post " + post.id + " created.", "success");
      result.classList.remove("hidden");
      result.innerHTML = "";
      var text = document.createElement("span");
      text.textContent = "Draft saved. ";
      var link = document.createElement("a");
      link.href = "/posts";
      link.className = "text-blue-600 dark:text-blue-400 font-medium hover:underline";
      link.textContent = "View it in Posts";
      result.appendChild(text);
      result.appendChild(link);
      loadDashboard();
    } catch (err) {
      window.toast(err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document
      .getElementById("quick-generate-form")
      .addEventListener("submit", onQuickGenerate);
    var revenueForm = document.getElementById("revenue-form");
    if (revenueForm) {
      revenueForm.addEventListener("submit", onRevenueLog);
    }
    document
      .getElementById("dashboard-retry")
      .addEventListener("click", loadDashboard);
    loadDashboard();
    loadAutomation();
    loadRevenue();
    loadTodayActions();
    loadGrowthChart();
    loadWeeklyDigest();
    loadTemplatePerf();
    loadSystemHealth();
    loadAiWidget();
    loadAccountsOverview();
    loadProducts().catch(function (err) {
      window.toast("Could not load products: " + err.message, "error");
    });
    setInterval(function () {
      if (document.visibilityState === "visible") {
        loadDashboard();
        loadAutomation();
        loadRevenue();
        loadTodayActions();
      }
    }, REFRESH_MS);
    if (todayActions.timer) {
      clearInterval(todayActions.timer);
    }
    todayActions.timer = setInterval(function () {
      if (document.visibilityState === "visible") {
        loadTodayActions();
      }
    }, TODAY_ACTIONS_MS);
    // Stop the health-stats polls when the page is hidden/unloaded.
    function stopHealthPolls() {
      ["chartTimer", "digestTimer", "tplTimer"].forEach(function (key) {
        if (healthStats[key]) {
          clearInterval(healthStats[key]);
          healthStats[key] = null;
        }
      });
      healthStats.seq++;
    }
    function startHealthPolls() {
      stopHealthPolls();
      healthStats.chartTimer = setInterval(function () {
        if (document.visibilityState === "visible") {
          loadGrowthChart();
        }
      }, 300000);
      healthStats.digestTimer = setInterval(function () {
        if (document.visibilityState === "visible") {
          loadWeeklyDigest();
        }
      }, 600000);
      healthStats.tplTimer = setInterval(function () {
        if (document.visibilityState === "visible") {
          loadTemplatePerf();
        }
      }, 900000);
    }
    startHealthPolls();
    // System health (60s) + AI widget (5min) polls with pagehide cleanup.
    function stopSysPolls() {
      ["timer", "aiTimer", "acctTimer"].forEach(function (key) {
        if (sysHealth[key]) {
          clearInterval(sysHealth[key]);
          sysHealth[key] = null;
        }
      });
      sysHealth.seq++;
    }
    function startSysPolls() {
      stopSysPolls();
      sysHealth.timer = setInterval(function () {
        if (document.visibilityState === "visible") {
          loadSystemHealth();
        }
      }, 60000);
      sysHealth.aiTimer = setInterval(function () {
        if (document.visibilityState === "visible") {
          loadAiWidget();
        }
      }, 300000);
      sysHealth.acctTimer = setInterval(function () {
        if (document.visibilityState === "visible") {
          loadAccountsOverview();
        }
      }, 90000);
    }
    startSysPolls();
    var healthRefresh = document.getElementById("health-refresh-btn");
    if (healthRefresh) {
      healthRefresh.addEventListener("click", loadSystemHealth);
    }
    window.addEventListener("pagehide", function () {
      if (todayActions.timer) {
        clearInterval(todayActions.timer);
        todayActions.timer = null;
      }
      todayActions.seq++;
      stopHealthPolls();
      stopSysPolls();
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && todayActions.timer) {
        clearInterval(todayActions.timer);
        todayActions.timer = null;
      } else if (document.visibilityState === "visible" && !todayActions.timer) {
        loadTodayActions();
        todayActions.timer = setInterval(function () {
          if (document.visibilityState === "visible") {
            loadTodayActions();
          }
        }, TODAY_ACTIONS_MS);
      }
      if (document.visibilityState === "hidden") {
        stopHealthPolls();
        stopSysPolls();
      } else if (!healthStats.chartTimer) {
        loadGrowthChart();
        loadWeeklyDigest();
        loadTemplatePerf();
        startHealthPolls();
      }
      if (document.visibilityState === "visible" && !sysHealth.timer) {
        loadSystemHealth();
        loadAiWidget();
        loadAccountsOverview();
        startSysPolls();
      }
    });
  });
})();
