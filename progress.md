# POD Automation — Progress

> Project: `D:\Projects\pod-automation` — FastAPI + SQLite + Jinja2/Tailwind/vanilla-JS dashboard for print-on-demand Facebook automation.
> Last audited: 2026-10-09 — verified against live codebase (95 route decorators = 87 API + 8 pages, 12 DB tables, CSS v4.0).

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Project skeleton (FastAPI, config, logging, health, base template) | ✅ Done |
| 2 | Database layer (SQLAlchemy models, schemas, CRUD services, seed) | ✅ Done |
| 3 | AI logic layer (Groq/OpenAI/mock providers, fallback, content generation) | ✅ Done |
| 4 | REST API routes (products, posts, AI, logs, settings, dashboard) | ✅ Done |
| 5 | Frontend dashboard (6 pages, Tailwind, vanilla JS) | ✅ Done |
| 6 | Final integration (Facebook publishing, Automation scheduler, hardening) | ✅ Done |
| 7 | Facebook Group Growth & Intent DM Engine (Group Content Studio, Cadence Helper, Lead & DM Funnel + `GroupLeads` table) | ✅ Done |
| 8 | Psychology & Anti-Spam Framework (US/EU subcultures, identity triggers, indirect selling, reach-down shield) | ✅ Done |
| 9 | POD GOD MODE (auto post-queue batch, bulk smart capture, 1-click DM outreach, revenue tracker) | ✅ Done |
| 10 | Full deletion & clean-start control (delete on all post statuses, bulk wipe, seed-once flag, Clear Dummy Data) | ✅ Done |
| 11 | AutoPilot → Automation rename (display name, modules, API, DB, logs) | ✅ Done |
| 12 | Premium obsidian pitch-black dark theme (high-contrast charcoal) | ✅ Done |
| 13 | Products page refinement (modal-inside delete, no bulk wipe, reseed) | ✅ Done |
| 14 | Soft-delete & restore from Activity Logs (snapshots, restore API + UI) | ✅ Done |
| 15 | Light/Dark glassmode isolation fix (revert bad globals, scope dark under `html.dark`) | ✅ Done |
| 16 | Post-Phase-15 hardening & UI polish (destructive-header guard, demo-safe wipe, CSS v4.0 tokens, mobile nav, Groups page, duplicate/schedule extras) | ✅ Done |
| 17 | DM Safety Layer — M1→M2 gap enforcement (5-min min), per-account hourly/daily DM rate limiter, fb_accounts table + counters, send-status endpoint, DM modal countdown, Settings DM Safety section | ✅ Done |
| 18 | Reply Check + Cold Follow-up Engine — attention buckets (reply_check/overdue/m2_waiting/cold), Check Reply modal (replied/no_reply/bounced), M3 cold follow-up + auto-copy, follow_up_sent 6th status, Today's Actions dashboard widget, server-side bucket filter + pagination, group_stats hooks | ✅ Done |
| 19 | Group Health Dashboard + Daily Stats — group_stats table (UNIQUE stat_date), daily snapshot entry (members/new/posts/comments/leads/revenue/notes), auto-computed funnel per day, inline SVG growth chart (2 lines: members + leads, 30d), weekly digest (this vs last + delta arrows), template performance table (per source_template: posted/leads/converted/rate/revenue), queue copy/posted timestamps + template_name | ✅ Done |
| 20 | Production Hardening — auto daily DB backup (keep last 7, manual run + download + delete + restore with pre-restore snapshot), Facebook token expiry tracking (30/14/7/1 day warnings + "I updated the token" button), AI usage tracker (per provider/model/day: calls, tokens, cost, success rate + monthly rollup + sparkline), System Health endpoint (DB/FB/AI/queue/backup/kill-switch), kill switch (blocks at scheduler + publish layers), log retention prune, rate limits on backup endpoints | ✅ Done |
| 21 | Ghost Profile & Multi-Account Manager — fb_accounts extended (handle, persona_name/avatar/bio/tone, niche_focus, health_status, warnings_count, restricted_until, lifetime counters, priority, notes), account_groups_blocked table (collision prevention), account rotation (priority/round_robin/niche_match), per-account rate limits, warning/ban/restore tracking, auto-assign orphans, persona_service (tone-driven M1/M2/M3 post-processing), Accounts page (8th page) with cards + Add/Edit modal + persona preview, Groups lead-row account badge + DM account dropdown, Dashboard Accounts Overview card, multi_account_enabled feature flag (default OFF, single-account behavior preserved) | ✅ Done |

## What works right now

- Dashboard, Products, Posts, AI Studio, Groups, Activity Logs, Settings pages (7 total) — all live off the REST API.
- AI caption/hashtag/variation generation with provider fallback + mock mode.
- Facebook publishing (dry-run default; live via Page token), manual + scheduled + Automation loop with idempotency guards.
- `ensure_schema()` migrates old SQLite files safely; seed data is idempotent.
- **Group Growth & Intent DM Engine** (`/groups` + AI Studio Group Engagement panel):
  - LINK-FREE viral post generator (`POST /api/groups/posts`) for Car & Bike niches with 1-click Copy Post Text.
  - Cadence Helper (`GET /api/groups/cadence`): randomized 3–5 min safety delay + live countdown widget.
  - Comment intent classifier (`POST /api/groups/classify`: High/Medium/Low) + 2-step DM funnel (Message 1 zero-link, Message 2 product link after reply) stored in SQLite `GroupLeads` table with status flow unsent → step1_sent → step2_sent/replied → converted (`/api/group-leads` CRUD + `/api/groups/funnel/stats`).
- **Psychology & Safety Framework** on top of the Group Engine:
  - US/UK/EU subculture lens (JDM, American Muscle, Biker Brotherhood, Vintage Restoration) + 7 triggers (tribal loyalty, nostalgia, debate-baiting, in-group validation, identity attachment, controversy, status validation); 10 templates incl. JDM vs Muscle, Brotherhood Oath, Restoration Soul, Gear Status Check (indirect selling).
  - Direct selling BANNED in group posts; status & gear validation framing baits organic "where did you get this?" comments; all links route only through the DM funnel.
  - Reach-down shield (`app/services/group_shield.py`): synonym-spin + hashtag rotation per post and zero-link/sales-pitch scrubbing enforced post-generation (verified: 20 niche/template combos link-free, 6/6 unique outputs).
- **POD GOD MODE (Phase 9)**:
  - Group Content Auto-Queue: "Auto-Generate Daily Batch (5)" in AI Studio creates 5 distinct link-free psychology posts (distinct templates, mixed car/bike) into the `group_post_queue` table; sidebar queue list with Copy, Edit (re-shielded), 1-button Copy & Mark Posted, Delete (`/api/groups/queue/*`).
  - Smart Capture: `GroupLeads` extended with `user_profile_link` + `conversion_value` (+ group tagging); `POST /api/groups/leads/bulk-parse` parses 10+ pasted comments at once (`Name:`/`Name -`/`Name |`/`@name`/bare formats, fb.com URL auto-captured), classifies, and instantly saves high-intent leads.
  - 1-Click DM Outreach: per-lead "Copy M1 & Open DM" copies zero-link Message 1 and opens the lead's Facebook profile (or FB search fallback) in a new tab; profile links editable from the DM modal.
  - Revenue Tracker: Dashboard "Group DM Revenue" panel (total ROI, converted count, avg/sale) logging $ per shirt/hoodie/mug via `GET /api/groups/revenue` + lead `conversion_value` PATCH.
  - All new columns/tables migrate via extended `ensure_schema()` (creates missing group tables, ALTERs missing columns idempotently).
- **Full deletion & clean-start control (Phase 10)**:
  - Delete button on EVERY post card across Draft/Scheduled/Published/Failed (backend published-delete refusal removed) with "Are you sure you want to delete this post?" confirmation (`DELETE /api/posts/{id}`).
  - Bulk bar on Posts page: per-card checkboxes + select-page, Delete Selected (n), and Clear All scoped to the active status tab (`POST /api/posts/bulk-delete` with ids or delete_all+status).
  - Seed-once flag (`demo_seed_done` in app_settings): demo data seeds exactly once; wiping never resurrects Cat Astronaut/Hiker Hoodie/etc.
   - Clear Dummy Data (`POST /api/settings/clear-dummy-data`): wipes all products (cascades posts), standalone posts, leads, queued posts; keeps settings/logs. Button lives strictly in Settings → Danger Zone (shared `window.clearDummyData` helper, dark-theme matched).
- **AutoPilot → Automation rename (Phase 11)**:
   - Display name `POD Facebook Automation Dashboard` (`.env`, `.env.example`, `config.py` default, `run.py`, README).
   - Code rename across 28 files (104 spots): `routers/autopilot.py` → `automation.py`, `schemas/autopilot.py` → `automation.py`, `services/scheduler/autopilot.py` → `automation.py`; `AutoPilot` → `Automation`, `AutoPilotStatus` → `AutomationStatus`; API `/api/autopilot/*` → `/api/automation/*` (frontend JS updated in lockstep).
   - `DATABASE_URL` `data/autopilot.db` → `data/automation.db` (live data copied via SQLite backup API, counts verified equal); logger `pod-autopilot` → `pod-automation`; theme key `pod-automation-theme`.
   - Verified: `py_compile` clean, app boots with 60 route decorators (53 API + 7 pages), `/api/automation/status|run-now|fill-queue` live.
- **Premium obsidian dark theme (Phase 12)**:
   - Root/body forced to `#090d16` (`html.dark`, `!important` backstop; body blue glow tint cut 20%→8%); sidebar/topbar `#0a0e1a` glass (`blur-xl`, `border-slate-800/80`).
   - All cards/modals/inputs forced to charcoal `#111726/90` with sharp `border-slate-800` (`!important` beats every navy rule); hover `bg-[#161e31]` + `border-slate-700`.
   - Sidebar active item per spec: `bg-indigo-600/20 + text-indigo-400 + border-l-4 indigo-500` (padding-compensated, zero layout shift).
   - Headings + stat numbers pure `#ffffff`; secondary labels `#94a3b8`; badges/focus-rings/clickability preserved; light mode untouched.
   - Verified: CSS braces balanced, 7/7 pages render 200 with new palette served.
- **Products page refinement (Phase 13)**:
   - Red `Delete Data` bulk-wipe button + tooltip removed from Products filter bar (wipe stays only in Settings → Danger Zone).
   - Row/card instant `Delete` buttons removed; clicking a row/card (or Edit) opens the Details/Edit modal, whose footer has a red `Delete Product` button (bottom-left, hidden in Add mode) → confirm (`Are you sure you want to delete this product?`) → `DELETE /api/products/{id}` → close + list refresh.
   - Re-seeded the 3 demo products + 3 draft posts into empty DBs (one-off script, startup seed-once logic untouched so future wipes stay wiped).
   - Verified: `node --check` clean, API roundtrip `3 → create(201) → delete(204) → 3`, 7/7 pages 200.
- **Soft-delete & restore from Activity Logs (Phase 14)**:
   - `activity_logs` gains `snapshot` (JSON of deleted rows), `entity_type`, `entity_id`, `restored` flag (migrated idempotently via extended `ensure_schema()`); schema exposes `restorable`/`has_snapshot`/`restored`.
   - Deletes capture snapshots before removal: single product (+ its posts), single post, bulk posts, and `clear_dummy_data` (products, posts, leads, queued posts).
   - `POST /api/logs/restore` (`{log_ids}`) re-inserts missing rows (original ids reused when free, FK-safe fallback to standalone), marks entries restored (idempotent re-restore skips), logs `items_restored`; plus `POST /api/products/restore-seed` for demo recovery when logs were cleared.
   - Logs page: select checkbox + per-row `Restore` on eligible deletion rows, header select-all, `Restore Selected` bulk bar, `restored` badge, `Selected item successfully restored!` toast + table refresh.
    - Verified: `py_compile` + `node --check` clean, 60 route decorators, roundtrips for product(+cascaded post), single post, bulk, and full wipe (`3 products/5 posts → wipe → restore → equal`), validation 422s, 4/4 pages 200.
- **Light/Dark glassmode isolation fix (Phase 15)**:
   - Reverted bad global v2.0 block from `app.css` (bare `html/body/main/.card/.glass-card/.sidebar` rules forcing `#030712`, `[data-theme]` selectors, stale `:root` vars) that broke light mode and left dark muted navy; verified zero matches remain.
   - Dark strictly scoped under `html.dark`/`.dark`: page `#050811`, sidebar/topbar `#090d18` + `border-slate-800/80`, cards (`.card/.glass-card/.glass` + Tailwind `bg-white`, `bg-slate-900/800`, `bg-gray-50/70` boxes) → `rgba(15,23,42,0.75)` + `blur(12px)` + `rgba(255,255,255,0.1)` border + `#f8fafc` text.
   - Light restore guarded by `html:not(.dark)`: body `#f8fafc`/`#0f172a`, cards/sidebar `#ffffff` pristine white; base light rules untouched.
   - `base.html`: body `dark:bg-[#050811]`, sidebar/topbar `dark:bg-[#090d18]`, CSS bumped to `app.css?v=4.0` (v4.0 token refactor: `:root` light tokens vs `html.dark` tokens, `.card/.glass-card/.glass/.glass-strong` + `.glass-card-hover` utilities, token-driven sidebar/topbar/modal/inputs); toggle verified (`app.js:initTheme()` + early head script toggle `.dark` on `<html>`, persisted `pod-automation-theme`).
   - Verified: braces balanced, no unscoped dark-color rules, template dark colors + cache-buster present.
- **Post-Phase-15 hardening & UI polish (Phase 16 — was live in code, now documented)**:
   - Destructive-action guard (`app/routers/deps.py` `X-Confirm-Delete` header): enforced on `POST /api/posts/bulk-delete`, `DELETE /api/logs/clear`, `POST /api/settings/clear-dummy-data`.
   - Demo-safe wipe: `clear_dummy_data(wipe_all=False)` deletes only `is_demo` rows (detaches real `Post/GroupLead.product_id → None` to protect revenue); full wipe needs `{wipe_all:true, confirmation:"WIPE ALL DATA"}` + header + typed prompt (Settings → Danger Zone two-step `window.clearDummyData`).
   - Posts extras: `POST /api/posts/{id}/duplicate|schedule|unschedule`, `PATCH` 400-mapping, bulk-delete 500-id cap + status-enum validation, always-visible bulk bar with scoped `Clear <Status>s`, caption Read-more clamp, `datetime-local min=now` + TZ label, publish dry-run note + 401/429 toasts.
   - Logs extras: `DELETE /api/logs/clear`, request-seq race guards, auto-refresh cleanup on `pagehide/visibilitychange`, Clear-Logs response handles both shapes.
   - Models/columns previously unlisted: `posts.publish_attempts/last_attempt_at/ai_provider/ai_model/facebook_post_id/error_message`, `is_demo` on products/posts/leads/queue + `backfill_demo_flags`, `activity_logs restorable/has_snapshot/restored` + `items_restored/queue_filled/seed_restored/post_failed/post_published` events, multi-key restore aliases (`group_leads/leads`, `group_post_queue/queued_posts`).
   - Frontend infra: mobile sidebar (`sidebar-toggle/backdrop`, slide-in <1024px), modal reparent-to-`body` anti-clip fix, shared `renderPagination/copyToClipboard/guardImage/statusBadge/confirmDialog` helpers, Products → Studio deep link (`/studio?product_id=` preselect), Groups cadence offline fallback + vibrate, page sizes (products/posts 10, groups 20, logs 25).
    - Verified: 60 route decorators counted live (53 API + 7 pages: `/, /products, /posts, /studio, /groups, /logs, /settings`).
- **DM Safety Layer (Phase 17)**: fb_accounts table + seeded default; M1→M2 minimum gap (dm_min_gap_seconds, default 300s) enforced server-side with 409 + reason; hourly cap (dm_hourly_cap, default 10) + daily cap (dm_daily_cap, default 20) via atomic counter reset; GET /api/group-leads/{id}/send-status + GET /api/dm-safety/status live; DM modal countdown with 30s poll; Settings → DM Safety section.
- **Reply Check + Cold Follow-up (Phase 18)**: GroupLead extended with last_checked_at, follow_up_due_at, follow_up_sent_at, follow_up_count, reply_state; app/services/lead_lifecycle.py (compute_lead_urgency, get_leads_needing_attention 1-query, mark_reply_checked, record_follow_up_sent); routes GET /api/group-leads/attention, POST /{id}/mark-reply, POST /{id}/follow-up, POST /bulk-mark-reply (cap 100); lead list gains bucket + offset alias + total; detail gains urgency; Attention Board + 60s seq-guarded poll; Check Reply modal (3 buttons); M3 template auto-copy + FB profile open; filter chips + sessionStorage persist; Dashboard Today's Actions card + 90s poll; follow_up_sent added as 6th LEAD_STATUS (full enum + funnel stats + dropdowns).
- **Group Health Dashboard (Phase 19)**: group_stats table (stat_date UNIQUE, member_count, new_members, posts_published, comments_received, leads_captured, m1_sent, m2_sent, converted, revenue, notes); GroupLead.source_template; GroupPostQueue.copied_at/posted_at/template_name; app/services/group_stats.py (compute_live_stats_for_date, upsert_daily_stat, get_stats_range with gap fill, get_weekly_digest, get_template_performance 1-query); routes GET/POST /api/stats/daily, GET /api/stats/today, GET /api/stats/weekly-digest, GET /api/stats/templates, POST /api/groups/queue/{id}/copy|mark-posted; Groups Today's Snapshot card + Log Stats modal; Dashboard Growth Chart (inline SVG, 2 lines, SVG-title tooltips) + Weekly Digest (delta arrows) + Template Performance table (top 3 highlight); stats_auto_compute + digest_week_start + chart_days settings.
- **Production Hardening (Phase 20)**: db_backups + ai_usage tables; backup_service (run_backup via sqlite3 backup API, list/delete/restore with pre-restore snapshot + restart_required flag, scheduled_backup_if_due hourly); ai_usage_service (record_ai_call non-fatal, get_usage_summary); health_service (6-section snapshot, 30s cache); log prune on retention; kill switch blocks scheduler + publish; routes GET /api/system/health, GET/POST/DELETE /api/system/backups[/{id}], POST /api/system/backups/{id}/restore, GET /api/system/ai-usage, GET /api/system/token-status, POST /api/system/kill-switch; Settings System & Backups section (backup list + Run Backup + AI usage mini-panel + token status banner); Dashboard System Health card (6 pills) + Token Warning banner + AI Usage mini-widget; token_added_at/token_expires_at auto-set on FB test-connection; backup_hour_utc/backup_keep_last/log_retention_days/ai cost rates settings.
- **Multi-Account & Ghost Persona (Phase 21)**: fb_accounts extended with 14 new cols (handle, persona_name/avatar/bio/tone, niche_focus, health_status, health_note, restricted_until, warnings_count, total_dms_sent, total_converted, total_revenue, last_active_at, priority, notes); account_groups_blocked table (UNIQUE account_id+group_name); app/services/account_service.py (create/update/delete with last-account guard, list_accounts 1-query usage, get_account_stats); app/services/persona_service.py (get_persona_signature, apply_persona_to_message — never touches URLs/placeholders); dm_safety extended with get_next_available_account (priority/round_robin/niche_match rotation + capacity + collision check), record_account_warning/ban/restore, block_account_from_group, is_account_blocked_from_group; routes GET/POST /api/accounts, GET/PATCH/DELETE /api/accounts/{id}, POST /api/accounts/{id}/warning|ban|restore|block-group, GET /api/accounts/{id}/performance, POST /api/accounts/auto-assign-orphans; accounts.html + accounts.js (8th page); Groups lead-row @handle badge + DM account dropdown + Unassigned tile + Auto-assign Selected bulk; Dashboard Accounts Overview card; settings multi_account_enabled (default OFF, preserves single-account behavior 100%), account_rotation_mode, account_collision_window_days, account_warning_pause_hours, account_ban_recovery_days, account_health_check_enabled; DM flow auto-picks account if lead.assigned_account_id is NULL; /api/dm-safety/status gains per-account breakdown; /api/system/health gains accounts section.

## How to run

```powershell
cd D:\Projects\pod-automation
.\.venv\Scripts\Activate.ps1
python run.py
```

- App: <http://127.0.0.1:8000>
- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>
- Stop: `Ctrl+C`
- Pages (8): `/, /products, /posts, /studio, /groups, /accounts, /logs, /settings`
- Routes: 95 decorators (87 API + 8 pages), 12 DB tables

## Before going live on Facebook

1. Set real `FACEBOOK_PAGE_ID` + `FACEBOOK_PAGE_ACCESS_TOKEN` in `.env` (never commit it).
2. Restart, then Settings → **Test Connection** must show valid + Page name.
3. Publish **one** test post from Posts, verify on Facebook.
4. Only then set `FACEBOOK_DRY_RUN=false` and `posting_enabled=true`.
5. Add at least 2 accounts on /accounts page (optional — multi-account) OR keep single account.
6. Set backup_enabled=true, pick backup_hour_utc, verify a manual backup runs successfully.
7. Confirm token_added_at is set (auto after Test Connection) — Dashboard shows days_left.
8. Verify kill_switch_active=false before publishing.
9. Run one test DM flow end-to-end: lead → M1 (link-free) → wait 5 min → mark replied → M2 (with link) → verify rate counters.

## Audit & Hardening Status - All Core Flows Verified

Full codebase audit executed across FastAPI/SQLAlchemy backend and Tailwind/vanilla-JS frontend (60 route decorators scanned, 0 duplicate path+method collisions).

**1. Code Duplication & Overwrite Check (fixed):**
- `app/database/session.py:get_db` now rolls back on error; `check_same_thread` only for SQLite (was unconditional).
- `ensure_schema()` hardened: quoted identifiers, allowlisted tables, callable/callable-default safe, single-commit atomic migration with rollback (was per-column commit, unquoted, wrong `NOT NULL DEFAULT` inference).
- `clear_dummy_data()` converted from N+1 ORM loop to batch `DELETE`s with try/rollback (was long-lock + half-wipe risk).
- Added canonical `.glass-card` / `.glass-card-hover` utilities in `app.css`; removed duplicate `.dark .topbar` rule; dead `.dark .bg-white/.bg-red-50/.bg-amber-50` selectors now also match `/80` glass markup.
- `get_provider()` dead path fixed to return first of fallback chain; `status.py` unknown-provider drift fixed (no longer silently reports `groq`).

**2. Backend Integrity & Exception Handling (fixed):**
- `POST /api/posts/bulk-delete`: validates status enum, positive ids, 500-id cap (was raw `int()` cast, unvalidated status, uncapped wipe).
- `PATCH /api/posts/{id}`, `POST .../schedule|unschedule`: now map service `ValueError` to 400 (was unhandled 500 via global handler).
- `PUT /api/settings`: validates all values before any write, rollback on failure (was partial-write risk).
- `GET /api/facebook/status` + `POST /test-connection`: try/except + logging, safe `aclose()` (was bare, non-FacebookError crashed to 500).
- `POST /api/groups/queue/generate-batch`: per-item AI error handling with partial-progress warning; invalid plan returns 422.
- `POST /api/group-leads`: `ValueError` mapped to 422 + creation logging.
- AI fallback: new `AIAuthError`/`AIRateLimitError` + `classify_provider_error()`; auth failures skip retries and jump to fallback; `record_generation` guarded so DB errors never mask AI errors; `_map_ai_error()` maps auth→502, rate-limit→429, and only product/post "not found" to 404 (was any "not found" substring, e.g. model-not-found → false 404).

**3. Frontend UI/UX & JS State (fixed):**
- `confirmDialog` listener leak fixed with `{ once: true }` (stacked confirms double-fired).
- `#generic-modal` now has a working × close button wired in `app.js` (was Escape/backdrop only).
- AI Studio Retry button now re-runs `state.lastRun` (was dead hide-only).
- Logs tab race fixed with request-seq guards; auto-refresh cleared on `pagehide`/`visibilitychange` (was background polling + last-write-wins).
- Group funnel stats silent `catch{}` now `console.warn` for diagnostics.
- Dark mode contrast: `.dark .text-gray-400` `#64748b`→`#94a3b8`, placeholder `#64748b`→`#94a3b8` + opacity 1; `#bulk-result` given glass bg/text (was border-only box).
- Verified: all `apiFetch` paths match routers (no 404s); no hardcoded white-on-white breakage; no duplicate delegated listeners.

**Verification:** `py_compile` clean on all touched backend files; `node --check` clean on `app/groups/logs/studio.js`; `classify_provider_error` 401→AIAuthError / 429→AIRateLimitError / generic→AIProviderError confirmed; FastAPI route table = 60 decorators (53 API + 7 pages), 0 duplicates.

## Possible next steps (not started)

- Real Facebook credentials + first live publish verification.
- Production deployment (gunicorn/uvicorn workers, external DB migration if scaling).
- Note: "Feature development intentionally paused — 30-day execution phase (organic group growth) in progress before any further code work."
