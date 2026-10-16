# POD Facebook Automation Dashboard

A FastAPI + SQLite dashboard that generates Facebook post content for
print-on-demand products with AI, schedules posts, and publishes them to a
Facebook Page through the Graph API — manually or via a background Automation
loop. The frontend is server-rendered Jinja2 + Tailwind + vanilla JS that talks
only to the built-in REST API.

## Requirements

- Python 3.11+
- pip
- A Meta developer app with a Facebook Page (only needed for live publishing;
  dry-run mode works without any credentials)

## Setup

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

### Linux / macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Then open <http://localhost:8000> (dashboard), <http://localhost:8000/docs>
(API docs) and <http://localhost:8000/api/health> (health check).

## Getting a Facebook Page ID and Page access token

These steps change over time, so always follow Meta's current developer docs.
At a high level:

1. Create an app at <https://developers.facebook.com/apps>.
2. Add the Facebook Login / Pages tooling to the app as described in the
   current docs.
3. Generate a **Page access token** with permission to post to the Page
   (historically the `pages_manage_posts` and `pages_read_engagement`
   permissions; confirm the current names in Meta's docs).
4. Prefer a long-lived token so the scheduler keeps working.
5. Copy the numeric **Page ID** from the Page's About section or the Graph API.
6. Put both values into `.env` as `FACEBOOK_PAGE_ID` and
   `FACEBOOK_PAGE_ACCESS_TOKEN`.
7. **Never commit the token.** `.env` is git-ignored; only `.env.example`
   (which contains no secrets) is tracked.

## Dry-run vs live mode

- `FACEBOOK_DRY_RUN=true` (default): publishing is simulated. No network call
  is made; the API returns a fake id prefixed `dryrun_`. The UI shows an amber
  dry-run banner.
- `FACEBOOK_DRY_RUN=false`: posts are really published to the Page. The app
  logs `LIVE MODE: posts will be published to Facebook` as a WARNING at
  startup and the settings page shows a red LIVE banner.

### Checklist before switching FACEBOOK_DRY_RUN to False

1. Set `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN` in `.env`.
2. Restart the app.
3. Open Settings and press **Test Connection** — it must report the token as
   valid with your Page name.
4. Publish **one** test post from the Posts page and verify it on Facebook.
5. Only then enable `posting_enabled` and the scheduler for hands-free runs.

## How the Automation loop works

- A single asyncio background task ticks every `SCHEDULER_INTERVAL_SECONDS`
  (minimum 10) when `SCHEDULER_ENABLED` is true.
- Each tick uses short-lived DB sessions: one to read settings/due posts, then
  a fresh session per post. Due `scheduled` posts (`scheduled_at <= now`,
  capped at `SCHEDULER_BATCH_SIZE`) are published one by one with a 2-second
  pause between posts, and no session is held open across a network call.
- A post is **claimed atomically** (`status -> publishing`) before the network
  call, so the scheduler tick, a manual **Publish**, and parallel processes can
  never publish the same post twice.
- Posts that fail stay `failed` and are not auto-retried by the scheduler
  (manual retry from the UI still works). A claim interrupted mid-flight
  (crash/timeout) is reclaimed back to `failed` after 15 minutes. Published
  posts are immutable.
- When the `posting_enabled` setting is `"false"`, ticks still run but skip
  publishing and record `{"skipped_reason": "posting_disabled"}`.
- **Fill Queue From Drafts** auto-schedules the oldest drafts into
  `posting_hours` (UTC, comma-separated `HH:MM`) slots for the next 7 days,
  capped at `posts_per_day` per calendar day, skipping past slots.

## Feature map

The dashboard has 8 pages: **Dashboard, Products, Posts, AI Studio, Groups,
Accounts, Activity Logs, Settings**.

### Content & publishing
- **AI Studio** generates captions, hashtags and 2–5 variations per product with
  a chosen tone (friendly/funny/urgent/inspirational/professional). Provider
  fallback (Groq ⇄ OpenAI) plus a deterministic **mock mode**
  (`AI_MOCK_MODE=true`) for offline work.
- **Products** are the POD items (title, niche, design/mockup/store URLs, price,
  tags, status). **Posts** are captions + hashtags + optional image, moving
  through `draft → scheduled → publishing → published` / `failed`. Posts can be
  duplicated, scheduled, unscheduled, bulk-deleted, and soft-restored from logs.
- **Publishing** goes through the Graph API. A post is atomically *claimed*
  before the network call, so a manual **Publish** and a scheduler tick can never
  double-post. Failures stay `failed` (manual retry works).

### Group Growth & Intent DM Engine (`/groups` + AI Studio panel)
- **Link-free group post generator** for car/bike niches using a psychology
  framework (US/UK/EU subcultures, identity triggers, indirect selling). Posts
  are scrubbed of links/sales pitch by the reach-down shield and synonym-spun so
  every output is unique.
- **Auto-queue**: "Auto-Generate Daily Batch" drops 5 distinct posts into the
  queue for 1-click Copy → paste into Facebook groups.
- **Lead funnel**: paste group comments into **Smart Capture**, which parses,
  classifies intent (High/Medium/Low) and saves leads. Each lead follows a
  two-step DM funnel — **Message 1 is zero-link**, **Message 2 carries the link
  only after the lead replies** — with status flow
  `unsent → step1_sent → step2_sent/replied → follow_up_sent → converted`.
- **Cadence helper** shows a randomized 3–5 minute safety delay between actions.
- **Group Health**: daily snapshots (members/new/posts/comments/leads/revenue),
  live funnel charts, weekly digest with deltas, and per-template performance.
- **Revenue tracker** logs `$` per conversion (shirt/hoodie/mug) and rolls up
  ROI on the Dashboard.

### DM Safety (anti-spam)
- Minimum M1→M2 gap (`dm_min_gap_seconds`, default 300s), per-account hourly and
  daily DM caps (`dm_hourly_cap` / `dm_daily_cap`, atomic counters). The DM
  modal shows a live countdown and the server returns `409` with a reason when a
  send would break a cap.

### Multi-account & persona rotation
- **Accounts** page manages Facebook pages/profiles with a persona
  (name/avatar/bio/tone), niche focus, priority and health state
  (active/warned/restricted/banned). Rotation modes: `priority`, `round_robin`,
  `niche_match`. Group collisions are prevented via `account_groups_blocked`.
- Gated by `multi_account_enabled` (default **OFF** — single-account behavior is
  preserved). Warning/ban/restore and orphan auto-assignment are supported.

### Operations
- **Backups**: automatic daily SQLite snapshot (retained N days) plus manual
  Run/Download/Delete/**Restore**. Restore takes a pre-restore snapshot and
  reports `restart_required`.
- **Kill switch**: an emergency stop that blocks publishing at *both* the
  scheduler and the publisher layers.
- **Token expiry tracking** (30/14/7/1-day warnings), **AI usage & cost**
  rollups, **system health** snapshot (DB/FB/AI/queue/backup/disk/accounts) and
  **log retention** pruning.
- **Activity Logs** capture deletions with snapshots so products/posts/leads/
  queue items can be restored from the Logs page.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| APP_NAME | POD Facebook Automation Dashboard | Display name |
| APP_ENV | development | Enables dev seed + CORS + reload |
| DEBUG | false | Uvicorn reload flag |
| HOST / PORT | 127.0.0.1 / 8000 | Server bind (loopback only) |
| CORS_ORIGINS | localhost:8000/3000/5173/8080 | Allowed browser origins (JSON list) |
| DATABASE_URL | sqlite:///./data/automation.db | SQLAlchemy URL |
| AI_PROVIDER | groq | Primary AI provider |
| GROQ_API_KEY / OPENAI_API_KEY | (empty) | AI keys (never exposed) |
| GROQ_MODEL / OPENAI_MODEL | qwen/qwen3.8-27b / gpt-4o-mini | Model ids |
| AI_TEMPERATURE / AI_MAX_TOKENS / AI_TIMEOUT_SECONDS | 0.8 / 800 / 30 | Generation tuning |
| AI_MAX_RETRIES / AI_FALLBACK_ENABLED / AI_MOCK_MODE | 3 / true / false | Retry + fallback + mock |
| DEFAULT_POST_LANGUAGE / DEFAULT_BRAND_VOICE | English / friendly, witty, and persuasive | Copy defaults |
| FACEBOOK_PAGE_ID / FACEBOOK_PAGE_ACCESS_TOKEN | (empty) | Publishing credentials |
| FACEBOOK_GRAPH_VERSION | v21.0 | Graph API version |
| FACEBOOK_DRY_RUN | true | Simulate publishing |
| SCHEDULER_ENABLED | true | Background loop on/off |
| SCHEDULER_INTERVAL_SECONDS | 30 | Tick interval (min 10) |
| SCHEDULER_BATCH_SIZE | 5 | Posts per tick |
| PUBLISH_MAX_ATTEMPTS | 3 | Auto-retry cap |
| LOG_LEVEL | INFO | Logging verbosity |

> **Security:** `.env` is git-ignored and must never be committed. If a provider
> key (`GROQ_API_KEY` / `OPENAI_API_KEY`) or the Facebook token was ever
> committed, pasted, or shared, **rotate it** at the provider and update `.env`.
> Unknown `.env` keys now fail startup (`extra="forbid"`) so typos can't
> silently fall back to defaults.

## Troubleshooting

- **Token expired / 401 "Facebook token invalid or expired"**: generate a fresh
  (preferably long-lived) Page token in Meta's tools, update `.env`, restart,
  and use **Test Connection**.
- **Rate limit / 429**: the client backs off and retries; the UI tells you to
  try again later. Lower `SCHEDULER_BATCH_SIZE` or raise
  `SCHEDULER_INTERVAL_SECONDS` to stay under limits.
- **Port in use**: another server is bound to 8000 — stop it or set `PORT` to
  a free port in `.env`.
- **SQLite locked / database is locked**: SQLite allows one writer at a time.
  The app uses WAL mode; avoid opening the DB in an external editor while the
  server runs, and do not run two servers against the same file.
- **AI 503 "No AI provider is configured"**: set a real `GROQ_API_KEY` or
  `OPENAI_API_KEY`, or enable `AI_MOCK_MODE=true` for offline work.
- **AI 502**: the provider call failed — check the key, model name, and
  network, then retry.

## Development

```bash
pip install -r requirements-dev.txt
pytest            # unit + API tests (isolated temp DB, mock AI, dry-run)
ruff check app    # lint
python -m compileall -q app   # byte-compile
```

`make check` runs all of the above plus a JavaScript syntax check. CI
(`.github/workflows/ci.yml`) runs the same on every push/PR.

## Project tree

```text
pod-automation/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── logging_config.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   ├── init_db.py
│   │   └── seed.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── product.py
│   │   ├── post.py
│   │   ├── ai_generation.py
│   │   ├── activity_log.py
│   │   ├── app_setting.py
│   │   ├── fb_account.py
│   │   ├── group_lead.py
│   │   ├── group_post_queue.py
│   │   ├── group_stats.py
│   │   └── system.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── dashboard.py
│   │   ├── facebook.py
│   │   ├── automation.py
│   │   ├── product.py
│   │   ├── post.py
│   │   ├── ai.py
│   │   ├── ai_generation.py
│   │   ├── activity_log.py
│   │   ├── app_setting.py
│   │   ├── group_lead.py
│   │   └── group_queue.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── product_service.py
│   │   ├── post_service.py
│   │   ├── ai_generation_service.py
│   │   ├── ai_usage_service.py
│   │   ├── account_service.py
│   │   ├── backup_service.py
│   │   ├── dm_safety.py
│   │   ├── group_service.py
│   │   ├── group_shield.py
│   │   ├── group_stats.py
│   │   ├── health_service.py
│   │   ├── lead_lifecycle.py
│   │   ├── log_service.py
│   │   ├── maintenance_service.py
│   │   ├── persona_service.py
│   │   ├── settings_service.py
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── exceptions.py
│   │   │   ├── groq_provider.py
│   │   │   ├── openai_provider.py
│   │   │   ├── mock_provider.py
│   │   │   ├── factory.py
│   │   │   ├── prompts.py
│   │   │   ├── parser.py
│   │   │   ├── client.py
│   │   │   ├── content_generator.py
│   │   │   └── status.py
│   │   ├── facebook/
│   │   │   ├── __init__.py
│   │   │   ├── exceptions.py
│   │   │   ├── client.py
│   │   │   ├── publisher.py
│   │   │   └── status.py
│   │   └── scheduler/
│   │       ├── __init__.py
│   │       └── automation.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   ├── health.py
│   │   ├── pages.py
│   │   ├── products.py
│   │   ├── posts.py
│   │   ├── ai.py
│   │   ├── logs.py
│   │   ├── settings.py
│   │   ├── dashboard.py
│   │   ├── facebook.py
│   │   ├── automation.py
│   │   ├── groups.py
│   │   ├── accounts.py
│   │   ├── stats.py
│   │   └── system.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── products.html
│   │   ├── posts.html
│   │   ├── studio.html
│   │   ├── groups.html
│   │   ├── accounts.html
│   │   ├── logs.html
│   │   └── settings.html
│   └── static/
│       ├── css/
│       │   └── app.css
│       └── js/
│           ├── app.js
│           ├── dashboard.js
│           ├── products.js
│           ├── posts.js
│           ├── studio.js
│           ├── groups.js
│           ├── accounts.js
│           ├── logs.js
│           └── settings.js
├── tests/
│   ├── conftest.py
│   ├── test_ai_classify.py
│   ├── test_confirm_header.py
│   ├── test_kill_switch.py
│   ├── test_publisher.py
│   ├── test_redaction.py
│   └── test_validation.py
├── data/
│   └── .gitkeep
├── logs/
│   └── .gitkeep
├── .github/
│   └── workflows/
│       └── ci.yml
├── .env.example
├── .gitignore
├── .python-version
├── AUDIT.md
├── Makefile
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── run.py
└── README.md
```
