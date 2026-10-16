# POD Automation — UI/UX + Whole-Project Audit
Date: 2026-10-16 | Auditor: OpenCode (Muse Spark) | Scope: `app/templates`, `app/static`, `app/* backend`, root config

> Weird = anything broken, inconsistent, insecure, or confusing. Ordered P0 (fix now) → P2 (polish).

---

## P0 — Broken / must fix

### 1. Orphan `index.html` — dead page, wasted maintenance
- `app/routers/pages.py:26-33` — `/` serves `dashboard.html`, not `index.html`.
- `index.html` is unreferenced anywhere (only `pages.py:31` references `dashboard.html`). It still loads `dashboard.js` but IDs don't match (`stat-products/posts/scheduled/...` vs JS expects `stat-total-products/stat-active-leads/...` → `TypeError: null`, dashboard shows "Could not load overview").
- **Fix:** delete `app/templates/index.html`, or keep only `dashboard.html`. Update `README.md:139-239` tree which still lists `index.html` and omits `dashboard.html/groups.html/accounts.html`.

### 2. `confirmDialog` hangs on Escape/backdrop dismiss
- `app/static/js/app.js:423-476,486-521` — Escape/backdrop calls `closeModal()` without resolving promise → any `await confirmDialog()` hangs forever, button stuck in loading state. Affects delete/publish/restore.
- **Fix:** resolve `false` on dismiss, reset button state in `finally`.

### 3. Bulk-delete filter duplication + destructive label
- `app/static/js/posts.js:429-442` — `loadFilters()` appends product options without clearing; called after every mutation → duplicate `<option>`s.
- `app/templates/posts.html:32` — button says `Clear [Drafts|...]` with `title="Delete every post…"` — label sounds like clear-filter, actually bulk-deletes. Should read `Delete all …`.
- **Fix:** clear select before append; rename button; keep existing confirm (`posts.js:336-343`).

### 4. Double-post / lost-attempt risk in publisher
- `app/services/facebook/publisher.py:49-52,84` — `publish_attempts+=1; commit()` *before* network call. If non-`FacebookError` escapes or `mark_post_published` DB write fails *after* FB accepted the post, retry double-posts. No `publishing` state / idempotency key.
- `app/services/scheduler/automation.py:32,105,144-165` — `_in_flight` set is dead under single-process `_lock`; zero protection across processes or manual `POST /publish` vs tick. Long session held open across `await publish + sleep(2)` (`:105-176`) → SQLite `database is locked` risk.
- **Fix:** DB claim (`UPDATE … WHERE status='scheduled'`), short-lived sessions per post, don't bump counter on dry-run/validation failure, validate non-empty message before increment.

### 5. Live `GROQ_API_KEY` on disk + fail-open defaults
- `.env:16` contains live `GROQ_API_KEY=gsk_…` (git-ignored but present, no rotation docs).
- `app/config.py:32-33` defaults `APP_ENV=development, DEBUG=True` → mis-deploy without prod `.env` silently runs debug + seeds demo data (`app/main.py:44-48`). `extra="ignore"` (`config.py:26-30`) silently swallows `.env` typos.
- `.env` only has 14/29 keys; missing `AI_TEMPERATURE/MAX_TOKENS/TIMEOUT/RETRIES/FALLBACK/MOCK_MODE`, `FACEBOOK_DRY_RUN/GRAPH_VERSION`, `SCHEDULER_*`, `PUBLISH_MAX_ATTEMPTS` → silent code defaults.
- **Fix:** `DEBUG=False` default, `extra="forbid"`, sync `.env` from `.env.example`, rotate the leaked key, document `CORS_ORIGINS` (in `config.py:39-50` but missing from `.env.example` + README env table).

---

## P1 — UX weirdness + backend gaps

### UI/UX
6. **Two card systems:** `dashboard.html:40-64` uses `.card.dash-card` (`app.css:903-1021` obsidian tokens); all other pages use Tailwind `bg-white/70 … rounded-xl shadow-lg`. Radii/shadows differ.
7. **`base.html:57,37,78`** — topbar/sidebar rely on `app.css` for `border-bottom/width` while Tailwind classes omit `border` width; winner depends on Play-CDN `<style>` vs `app.css?v=4.0` order — fragile. `max-w-6xl mx-auto` squeezes wide tables → forced `overflow-x-auto` on desktop even.
8. **`logs.html:34`** — `class="hidden … flex …"` display conflict; JS (`logs.js:43-56`) only toggles `hidden`.
9. **No desktop sidebar collapse** (`app.css:164-194` fixed 16rem; mobile slide-over only). No sticky Save/Reset on 22-field `settings.html:20,217-220` (long scroll). `studio.html:8` controls stack above results on mobile → long scroll before `studio-results:116`.
10. **Timezone inconsistency:** `app.js:223-235` local no-TZ suffix; `logs.js:130,283` + backup hour UTC; posting hours (`settings.html:65-71`) unlabeled TZ; schedule modal (`posts.html:98`, `posts.js:547-548`) local + TZ label; `dashboard.html:53` says `(UTC)`. Pick one + always label.
11. **Bulk bar always visible** (`posts.html:24`, `posts.js:278` never hides) → `0 selected / Delete Selected[disabled] / Clear All` on empty list. Select-all (`posts.js:756-766`) does full `loadPosts()` refetch → flicker + focus loss.
12. **Regenerate overwrites with no preview/confirm/undo** (`posts.html:110-131`, `posts.js:592-611`). `settings.html:243` Reset discards edits without dirty-check. Destructive confirms mix custom modal + blocking native `prompt` (`app.js:383` WIPE, `settings.js:377` RESTORE).
13. **Stale-state races:** `products.js:185-221`, `posts.js:368-416`, `studio.js:136-152` have no request-seq guard (unlike `dashboard.js:231,234` + `logs.js:78-83`). `studio.js:5` `state.lastAction` dead (`141` writes `lastRun`); group batch `return []` → `renderResults([])` unhides `studio-empty:113` under result.
14. **`posts.js:568`** `new Date(raw).toISOString()` throws `RangeError` outside `try` (before `try:571`) → uncaught, no inline error. `settings.js:619-631` 422 fuzzy `message.indexOf(key)` splats one error to many fields. `settings.js:525-527,560-563` card-load catch → toast only, leaves blank card (skeleton+content both hidden).
15. **Copy jargon:** `products.html:33` "Seed products are fully editable…", `settings.html:167` "I updated the token" (actually just POSTs `/token-refresh-note`, no validation), `revenue-form` placeholder helpful but `$0.00/0` flash before load (`index.html:127`).

### Accessibility (all `file:line` verified)
16. Toggles use `span.field-label + aria-labelledby`, not `<label>` — clicking text does nothing (`settings.html:50,121,136,186`). Smart-capture modal labels lack `for` (`studio.js:301-312`). Post checkbox announces ID only (`posts.js:145`).
17. Tone pills (`studio.html:18-24`) no `aria-pressed`; Settings radiogroup no arrow-key handling (`settings.html:256`, `settings.js:37-43`); Logs tabs click-only, no `aria-controls`/arrow nav (`logs.html:9-12`, `logs.js:405-420`); `index.html:107-112` table missing `scope=col`, `Conv` unexplained; charts `role=img` empty + color-only legend (`index.html:91,88-89,232`).
18. No `aria-live` on `quick-generate-result`, `queue-counts`, `posts-selected-count`, `post-caption-count`. No focus trap in modals (`app.js:423-457` focuses first control but background tabbable). Sidebar toggle lacks `aria-expanded/controls`, no Escape close (`base.html:58`, `app.js:766-798`).
19. `text-gray-400/text-xs` hints ≈2.8:1 on white — fails AA (`index.html:46,51…`, `settings.html:248,261`). `base.html:27` Tailwind CDN unpinned, no SRI/fallback → CDN fail = unstyled.
20. Good (don't regress): all buttons have `type=`, XSS-clean (`textContent` everywhere, `innerHTML` only `""` clears + escaped `statusBadge` at `app.js:686-690`), toast `aria-live` + `role=status/alert` correct.

### Backend robustness
21. **Validation gaps:** `schemas/post.py:17` `image_url` length-only (no `HttpUrl` → SSRF via `publisher.py:64`); `status: PostStatus` accepted on create lets client forge `published` bypassing `mark_post_published`; `schemas/ai.py:10-32` tone silently normalizes to `friendly` instead of 422; single `DELETE /posts/{id}` + `DELETE /products/{id}` need no `X-Confirm-Delete` while bulk does (`routers/posts.py:51-55,162-179`).
22. **Config clamping hides errors:** `SCHEDULER_INTERVAL_SECONDS ge=10` but `automation.py:53,96` does `max(10,…)` — never surfaces 422. `BATCH_SIZE/PUBLISH_MAX_ATTEMPTS/AI_TEMPERATURE/MAX_TOKENS/TIMEOUT/RETRIES` unbounded. `logging_config.py:13` invalid `LOG_LEVEL` silently → INFO. `GROQ_MODEL=qwen/qwen3.8-27b` (`config.py:66`) looks like typo — verify vs Groq docs.
23. **AI retry bugs:** `services/ai/client.py:131-132` `time.sleep` blocks event-loop worker (up to ~6s/request); `content_generator.py:55-60` double-wraps `run_with_fallback` → up to 12 provider calls; `regenerate_caption/generate_hashtags/generate_variations (:75,79,91)` have no parse-retry unlike `:55-60`; `AIResponseParseError` never tries next provider; `_safe_record` `db.rollback()` can wipe caller's staged `Post`; SDK `timeout:int` raw, SDK retries not disabled (stack on ours); `MockProvider` with `provider="mock"` looks real if `AI_MOCK_MODE` leaks to prod.
24. **Partial-commit / perf:** `routers/groups.py:131-148` 502 after partial `save_queued_post` commits (need transaction or `207 partial`); `groups.py:252` loads 10k ORM objects to filter in Python (OOM/DoS); `post_service.py:140-149` loads all overdue then `[:batch]` (add `.limit`); per-ID `get_post` loop + `bulk_delete` re-query = 2N+1 queries (`routers/posts.py:86-87`); `health_service.py:45,77,95,117` returns `str(exc)[:200]` (DB path disclosure); `system.py:93-107` `FileResponse(file_path)` no confinement to `data/backups/`; `system.py:60-69` 30s health cache no lock; `backup_service.py:212-259` overwrites live SQLite while request session open, "restart required" not enforced; `init_db.py:55-72` callable defaults → `DEFAULT 0` for new NOT NULL timestamps.
25. **Status-code drift:** `ValueError→400` in posts but `→422` in system backup/restore; FB auth →401 vs AI auth →502; `POST /generate→201` but group creates →200. Pick one semantic each.
26. **Zero tests:** no `tests/`, `pytest.ini`, `pyproject.toml`, lint/format/typecheck, or CI (`.github/` absent). Zero coverage for redaction, publisher idempotency, tick kill-switch, fallback matrix, `require_destructive_confirmation`.

---

## P2 — Project hygiene

27. **README drift (Phase-6-era):** tree (`README.md:139-239`) missing `dashboard/groups/accounts.html`, `routers/{accounts,groups,stats,system,deps}.py`, 6 extra models, `schemas/{group_lead,group_queue}.py`, 11 extra services (`account/backup/dm_safety/group*/health/lead_lifecycle/maintenance/persona/ai_usage`), `static/js/{groups,accounts}.js`. Feature docs stop at scheduler basics — zero docs for Group/DM funnel, DM Safety caps, backups/restore, kill-switch, multi-account rotation (all done per `progress.md:18-31`). Only `progress.md:4` acknowledges Phases 7-21.
28. **Deps:** all `==` pinned (good) but no lockfile/hashes, no Dependabot, no `.python-version` / `requires-python` (README says 3.11+, venv is 3.12), `python-multipart==0.0.20` superseded, no prod server config (only dev `run.py` reload; `progress.md:160` notes as next step).
29. **`.gitignore` gaps:** only bare `.env` (add `.env*` + `!.env.example`); `*.sqlite-wal/-shm` not covered; root `*.log/*.out` not covered; missing `.pytest_cache/.ruff_cache/.mypy_cache/.coverage/htmlcov/*.bak` (harmless now, bites later). Verified ignored correctly: `.env`, `data/automation.db`, `logs/app.log`, `data/backups/*.db`.
30. **Leftover files:** `data/autopilot.db` pre-Phase-11 rename artifact still on disk (`progress.md:61`); `index.html` orphan; `ai_generation_service.py:56-60 clear_generations()` + `log_service.py:103-107 clear_logs()` dead (no router); duplicate `_RESTORE_CONFIRM_TEXT` (`backup_service.py:16-17` vs `routers/system.py:27-28`); `seed.py:90-100` matches demo rows by title/caption strings (collides with user rows); `seed.py:115-157` double `db.close()`; `products.js:131,165` `"$"+price` no `toFixed(2)`; `logs.js:53-54` dead ternary (identical branches).
31. **Missing scaffolding:** no `Dockerfile/docker-compose.yml`, `LICENSE`, `CHANGELOG/CONTRIBUTING`, `.python-version`, `pyproject.toml`, CI workflows, `Makefile`. `run.py:8-20` dev-only (no `--host/--port/--no-reload`, no pre-boot env validation).

---

## Recommended fix order
1. Delete `index.html` + sync README tree (§1, §27).
2. Fix `confirmDialog` dismiss (§2) + `loadFilters` clear + rename Clear→Delete (§3).
3. Publisher idempotency + scheduler session/claim (§4).
4. Env hardening + key rotation (§5).
5. Timezone labels, bulk-bar hide, seq-guards, date-parse guard (§10-14).
6. A11y label/live-region/focus pass (§16-18).
7. Add `tests/` + CI + lockfile (§26, §28).
