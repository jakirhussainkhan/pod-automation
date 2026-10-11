/* Logs page: activity table and AI generations with expandable rows. */
(function () {
  "use strict";

  var LOG_PAGE_SIZE = 25;
  var GEN_PAGE_SIZE = 25;
  var logState = { skip: 0, total: 0, level: "" };
  var genState = { skip: 0, total: 0 };
  var autoTimer = null;
  var logRequestSeq = 0;
  var genRequestSeq = 0;
  var RESTORABLE_EVENTS = ["product_deleted", "post_deleted", "posts_bulk_deleted", "dummy_data_cleared"];
  var selectedLogs = new Set();

  /**
   * Check whether a log entry can be restored (deletion with snapshot).
   * @param {Object} entry - Activity log entry.
   * @returns {boolean} True when a Restore action applies.
   */
  function isRestorable(entry) {
    if (!entry) {
      return false;
    }
    if (entry.restored) {
      return false;
    }
    var flag = entry.restorable;
    if (flag === undefined) {
      flag = RESTORABLE_EVENTS.indexOf(entry.event_type) !== -1;
    }
    if (!flag) {
      return false;
    }
    if (entry.has_snapshot === false) {
      return false;
    }
    return true;
  }

  /**
   * Refresh the bulk restore bar for the current selection.
   */
  function updateRestoreBar() {
    var bar = document.getElementById("logs-restore-bar");
    var count = document.getElementById("logs-restore-count");
    if (!bar || !count) {
      return;
    }
    if (selectedLogs.size === 0) {
      bar.classList.add("hidden");
    } else {
      bar.classList.remove("hidden");
      count.textContent =
        selectedLogs.size + (selectedLogs.size === 1 ? " selected" : " selected");
    }
  }

  /**
   * Load activity logs for the current filter.
   */
  async function loadLogs() {
    var loading = document.getElementById("logs-loading");
    var errorBox = document.getElementById("logs-error");
    var empty = document.getElementById("logs-empty");
    var table = document.getElementById("logs-table");
    var tbody = document.getElementById("logs-tbody");
    loading.classList.remove("hidden");
    errorBox.classList.add("hidden");
    empty.classList.add("hidden");
    table.classList.add("hidden");
    tbody.innerHTML = "";
    var params = new URLSearchParams();
    params.set("skip", String(logState.skip));
    params.set("limit", String(LOG_PAGE_SIZE));
    if (logState.level) {
      params.set("level", logState.level);
    }
    var requestId = ++logRequestSeq;
    try {
      var data = await window.apiFetch("/api/logs?" + params.toString());
      if (requestId !== logRequestSeq) {
        return; // A newer tab switch / refresh superseded this response.
      }
      logState.total = data.total;
      loading.classList.add("hidden");
      if (data.items.length === 0) {
        empty.classList.remove("hidden");
      } else {
        table.classList.remove("hidden");
        // Drop selections for entries no longer on this page.
        var visibleIds = {};
        data.items.forEach(function (entry) {
          visibleIds[entry.id] = true;
        });
        Array.from(selectedLogs).forEach(function (id) {
          if (!visibleIds[id]) {
            selectedLogs.delete(id);
          }
        });
        data.items.forEach(function (entry) {
          var row = document.createElement("tr");
          row.className = "border-b border-gray-200 dark:border-slate-700 last:border-0 hover:bg-white/90 dark:hover:bg-slate-800/80";
          var selectCell = document.createElement("td");
          selectCell.className = "px-3 py-2";
          var eligible = isRestorable(entry);
          if (eligible) {
            var checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "w-4 h-4 log-restore-select";
            checkbox.value = String(entry.id);
            checkbox.checked = selectedLogs.has(entry.id);
            checkbox.setAttribute("aria-label", "Select log #" + entry.id + " for restore");
            checkbox.addEventListener("change", function (event) {
              var id = Number(event.target.value);
              if (event.target.checked) {
                selectedLogs.add(id);
              } else {
                selectedLogs.delete(id);
              }
              updateRestoreBar();
              syncSelectAll();
            });
            selectCell.appendChild(checkbox);
          } else {
            selectCell.textContent = "—";
            selectCell.classList.add("text-gray-300", "dark:text-slate-600");
          }
          var time = document.createElement("td");
          time.className = "px-3 py-2 whitespace-nowrap text-gray-500 dark:text-slate-400";
          time.textContent = window.formatDate(entry.created_at);
          var level = document.createElement("td");
          level.className = "px-3 py-2";
          level.innerHTML = window.statusBadge(entry.level);
          var eventCell = document.createElement("td");
          eventCell.className = "px-3 py-2 font-mono text-xs";
          eventCell.textContent = entry.event_type;
          var message = document.createElement("td");
          message.className = "px-3 py-2";
          message.textContent = entry.message;
          var post = document.createElement("td");
          post.className = "px-3 py-2";
          post.textContent = entry.post_id === null || entry.post_id === undefined ? "—" : "#" + entry.post_id;
          var action = document.createElement("td");
          action.className = "px-3 py-2 whitespace-nowrap";
          if (eligible) {
            var restoreBtn = document.createElement("button");
            restoreBtn.type = "button";
            restoreBtn.className = "btn btn-secondary btn-sm log-restore-btn";
            restoreBtn.textContent = "Restore";
            restoreBtn.setAttribute("data-log-id", String(entry.id));
            restoreBtn.addEventListener("click", function () {
              restoreLogs([Number(restoreBtn.getAttribute("data-log-id"))], restoreBtn);
            });
            action.appendChild(restoreBtn);
          } else if (entry.restored) {
            var done = document.createElement("span");
            done.className = "badge badge-green";
            done.textContent = "restored";
            action.appendChild(done);
          } else {
            action.textContent = "—";
          }
          row.appendChild(selectCell);
          row.appendChild(time);
          row.appendChild(level);
          row.appendChild(eventCell);
          row.appendChild(message);
          row.appendChild(post);
          row.appendChild(action);
          tbody.appendChild(row);
        });
        updateRestoreBar();
        syncSelectAll();
      }
      window.renderPagination(
        document.getElementById("logs-pagination"),
        { total: data.total, skip: logState.skip, limit: LOG_PAGE_SIZE },
        function (nextSkip) {
          logState.skip = nextSkip;
          loadLogs();
        }
      );
    } catch (err) {
      loading.classList.add("hidden");
      document.getElementById("logs-error-text").textContent =
        "Could not load logs: " + err.message;
      errorBox.classList.remove("hidden");
    }
  }

  /**
   * Restore soft-deleted rows captured in the given log entries.
   * @param {number[]} ids - Activity log ids to restore.
   * @param {HTMLButtonElement} [btn] - Trigger button for loading state.
   */
  async function restoreLogs(ids, btn) {
    var unique = Array.from(new Set((ids || []).map(Number).filter(function (n) { return n > 0; })));
    if (unique.length === 0) {
      window.toast("Select at least one deletion entry to restore.", "info");
      return;
    }
    if (btn) {
      window.setButtonLoading(btn, true, "Restoring…");
    }
    try {
      var result = await window.apiFetch("/api/logs/restore", {
        method: "POST",
        body: JSON.stringify({ log_ids: unique })
      });
      var restored = result && typeof result.restored_logs === "number" ? result.restored_logs : unique.length;
      unique.forEach(function (id) {
        selectedLogs.delete(id);
      });
      updateRestoreBar();
      await loadLogs();
      if (restored > 0) {
        window.toast("Selected item successfully restored!", "success");
      } else {
        window.toast("Nothing to restore: entries already restored or have no snapshot.", "info");
      }
    } catch (err) {
      window.toast("Could not restore: " + err.message, "error");
    } finally {
      if (btn) {
        window.setButtonLoading(btn, false);
      }
    }
  }

  /**
   * Sync the header select-all checkbox with the eligible rows on screen.
   */
  function syncSelectAll() {
    var master = document.getElementById("logs-select-all");
    if (!master) {
      return;
    }
    var boxes = Array.prototype.slice.call(document.querySelectorAll(".log-restore-select"));
    if (boxes.length === 0) {
      master.checked = false;
      master.indeterminate = false;
      return;
    }
    var checked = boxes.filter(function (box) { return box.checked; }).length;
    master.checked = checked > 0 && checked === boxes.length;
    master.indeterminate = checked > 0 && checked < boxes.length;
  }

  /**
   * Load AI generation records.
   */
  async function loadGenerations() {
    var loading = document.getElementById("gen-loading");
    var errorBox = document.getElementById("gen-error");
    var empty = document.getElementById("gen-empty");
    var table = document.getElementById("gen-table");
    var tbody = document.getElementById("gen-tbody");
    loading.classList.remove("hidden");
    errorBox.classList.add("hidden");
    empty.classList.add("hidden");
    table.classList.add("hidden");
    tbody.innerHTML = "";
    var params = new URLSearchParams();
    params.set("skip", String(genState.skip));
    params.set("limit", String(GEN_PAGE_SIZE));
    var genRequestId = ++genRequestSeq;
    try {
      var data = await window.apiFetch("/api/ai/generations?" + params.toString());
      if (genRequestId !== genRequestSeq) {
        return; // Superseded by a newer tab switch.
      }
      genState.total = data.total;
      loading.classList.add("hidden");
      if (data.items.length === 0) {
        empty.classList.remove("hidden");
      } else {
        table.classList.remove("hidden");
        data.items.forEach(function (gen) {
          var row = document.createElement("tr");
          row.className = "border-b border-gray-200 dark:border-slate-700 last:border-0 hover:bg-white/90 dark:hover:bg-slate-800/80";
          var time = document.createElement("td");
          time.className = "px-3 py-2 whitespace-nowrap text-gray-500 dark:text-slate-400";
          time.textContent = window.formatDate(gen.created_at);
          var provider = document.createElement("td");
          provider.className = "px-3 py-2";
          provider.textContent = gen.provider;
          var model = document.createElement("td");
          model.className = "px-3 py-2 font-mono text-xs";
          model.textContent = gen.model;
          var result = document.createElement("td");
          result.className = "px-3 py-2";
          var badge = document.createElement("span");
          badge.className = "badge " + (gen.success ? "badge-green" : "badge-red");
          badge.textContent = gen.success ? "success" : "failed";
          result.appendChild(badge);
          var tokens = document.createElement("td");
          tokens.className = "px-3 py-2";
          tokens.textContent =
            gen.tokens_used === null || gen.tokens_used === undefined
              ? "\u2014"
              : String(gen.tokens_used);
          var details = document.createElement("td");
          details.className = "px-3 py-2";
          var toggle = document.createElement("button");
          toggle.type = "button";
          toggle.className = "btn btn-secondary btn-sm";
          toggle.textContent = "Show";
          toggle.setAttribute("aria-expanded", "false");
          details.appendChild(toggle);
          row.appendChild(time);
          row.appendChild(provider);
          row.appendChild(model);
          row.appendChild(result);
          row.appendChild(tokens);
          row.appendChild(details);
          tbody.appendChild(row);

          var detailRow = document.createElement("tr");
          detailRow.className = "hidden border-b border-gray-200 dark:border-slate-700";
          var detailCell = document.createElement("td");
          detailCell.colSpan = 6;
          detailCell.className = "px-3 py-2 space-y-2";
          var promptLabel = document.createElement("p");
          promptLabel.className = "text-xs font-semibold text-gray-500 dark:text-slate-400";
          promptLabel.textContent = "Prompt";
          var promptBlock = document.createElement("pre");
          promptBlock.className = "code-block";
          promptBlock.textContent = gen.prompt;
          var responseLabel = document.createElement("p");
          responseLabel.className = "text-xs font-semibold text-gray-500 dark:text-slate-400";
          responseLabel.textContent = "Response";
          var responseBlock = document.createElement("pre");
          responseBlock.className = "code-block";
          responseBlock.textContent = gen.response;
          detailCell.appendChild(promptLabel);
          detailCell.appendChild(promptBlock);
          detailCell.appendChild(responseLabel);
          detailCell.appendChild(responseBlock);
          detailRow.appendChild(detailCell);
          tbody.appendChild(detailRow);

          toggle.addEventListener("click", function () {
            var shown = detailRow.classList.toggle("hidden");
            toggle.textContent = shown ? "Show" : "Hide";
            toggle.setAttribute("aria-expanded", shown ? "false" : "true");
          });
        });
      }
      window.renderPagination(
        document.getElementById("gen-pagination"),
        { total: data.total, skip: genState.skip, limit: GEN_PAGE_SIZE },
        function (nextSkip) {
          genState.skip = nextSkip;
          loadGenerations();
        }
      );
    } catch (err) {
      loading.classList.add("hidden");
      document.getElementById("gen-error-text").textContent =
        "Could not load generations: " + err.message;
      errorBox.classList.remove("hidden");
    }
  }

  /**
   * Clear all activity logs and AI generation history after confirmation,
   * then refresh both views.
   * @param {HTMLButtonElement} btn - Trigger button for loading state.
   */
  async function clearLogs(btn) {
    var confirmed = await window.confirmDialog(
      "Are you sure you want to clear all system logs?",
      { confirmText: "Clear Logs", danger: true }
    );
    if (!confirmed) {
      return;
    }
    window.setButtonLoading(btn, true, "Clearing\u2026");
    try {
      var result = await window.apiFetch("/api/logs/clear", {
        method: "DELETE",
        headers: { "X-Confirm-Delete": "true" }
      });
      var total =
        result && typeof result.deleted === "number"
          ? result.deleted
          : (result.deleted_logs || 0) + (result.deleted_generations || 0);
      logState.skip = 0;
      genState.skip = 0;
      selectedLogs.clear();
      await loadLogs();
      await loadGenerations();
      window.toast("Cleared " + total + " log entries.", "success");
    } catch (err) {
      window.toast("Could not clear logs: " + err.message, "error");
    } finally {
      window.setButtonLoading(btn, false);
    }
  }

  /**
   * Switch between the two tabs.
   * @param {string} name - Active tab name.
   */
  function switchTab(name) {
    var activity = name === "activity";
    document.getElementById("panel-activity").classList.toggle("hidden", !activity);
    document.getElementById("panel-generations").classList.toggle("hidden", activity);
    var tabA = document.getElementById("tab-activity");
    var tabG = document.getElementById("tab-generations");
    tabA.classList.toggle("pill-active", activity);
    tabG.classList.toggle("pill-active", !activity);
    tabA.setAttribute("aria-selected", activity ? "true" : "false");
    tabG.setAttribute("aria-selected", activity ? "false" : "true");
    if (activity) {
      loadLogs();
    } else {
      loadGenerations();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("tab-activity").addEventListener("click", function () {
      switchTab("activity");
    });
    document.getElementById("tab-generations").addEventListener("click", function () {
      switchTab("generations");
    });
    document.getElementById("log-level").addEventListener("change", function (event) {
      logState.level = event.target.value;
      logState.skip = 0;
      loadLogs();
    });
    document.getElementById("log-refresh").addEventListener("click", loadLogs);
    document.getElementById("logs-retry").addEventListener("click", loadLogs);
    document.getElementById("gen-retry").addEventListener("click", loadGenerations);
    var clearBtn = document.getElementById("logs-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        clearLogs(clearBtn);
      });
    }
    var restoreSelectedBtn = document.getElementById("logs-restore-selected");
    if (restoreSelectedBtn) {
      restoreSelectedBtn.addEventListener("click", function () {
        restoreLogs(Array.from(selectedLogs), restoreSelectedBtn);
      });
    }
    var restoreClearBtn = document.getElementById("logs-restore-clear");
    if (restoreClearBtn) {
      restoreClearBtn.addEventListener("click", function () {
        selectedLogs.clear();
        document.querySelectorAll(".log-restore-select").forEach(function (box) {
          box.checked = false;
        });
        updateRestoreBar();
        syncSelectAll();
      });
    }
    var selectAll = document.getElementById("logs-select-all");
    if (selectAll) {
      selectAll.addEventListener("change", function (event) {
        var boxes = document.querySelectorAll(".log-restore-select");
        boxes.forEach(function (box) {
          box.checked = event.target.checked;
          var id = Number(box.value);
          if (event.target.checked) {
            selectedLogs.add(id);
          } else {
            selectedLogs.delete(id);
          }
        });
        updateRestoreBar();
      });
    }
    document
      .getElementById("log-autorefresh")
      .addEventListener("change", function (event) {
        if (autoTimer) {
          clearInterval(autoTimer);
          autoTimer = null;
        }
        if (event.target.checked) {
          autoTimer = setInterval(function () {
            if (document.visibilityState === "visible") {
              loadLogs();
            }
          }, 15000);
        }
      });
    // Stop polling when the page is hidden/unloaded so background tabs
    // don't keep fetching.
    window.addEventListener("pagehide", function () {
      if (autoTimer) {
        clearInterval(autoTimer);
        autoTimer = null;
      }
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && autoTimer) {
        var box = document.getElementById("log-autorefresh");
        if (box) {
          box.checked = false;
        }
        clearInterval(autoTimer);
        autoTimer = null;
      }
    });
    loadLogs();
  });
})();
