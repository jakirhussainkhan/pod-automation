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
- Each tick opens its own DB session, loads due `scheduled` posts
  (`scheduled_at <= now`, capped at `SCHEDULER_BATCH_SIZE`), and publishes them
  one by one with a 2-second pause between posts.
- An asyncio lock plus an in-memory in-flight set guarantees a post is never
  published twice concurrently, including when **Run Now** fires during a tick.
- Posts that fail stay `failed` and are not auto-retried once
  `publish_attempts >= PUBLISH_MAX_ATTEMPTS` (manual retry from the UI still
  works). Published posts are immutable and can never be published twice.
- When the `posting_enabled` setting is `"false"`, ticks still run but skip
  publishing and record `{"skipped_reason": "posting_disabled"}`.
- **Fill Queue From Drafts** auto-schedules the oldest drafts into
  `posting_hours` (UTC, comma-separated `HH:MM`) slots for the next 7 days,
  capped at `posts_per_day` per calendar day, skipping past slots.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| APP_NAME | POD Facebook Automation Dashboard | Display name |
| APP_ENV | development | Enables dev seed + CORS + reload |
| DEBUG | true | Uvicorn reload flag |
| HOST / PORT | 127.0.0.1 / 8000 | Server bind |
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

## Project tree

```text
pod-automation/
├── app/
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
│   │   └── app_setting.py
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
│   │   └── app_setting.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── product_service.py
│   │   ├── post_service.py
│   │   ├── ai_generation_service.py
│   │   ├── log_service.py
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
│   │   ├── health.py
│   │   ├── pages.py
│   │   ├── products.py
│   │   ├── posts.py
│   │   ├── ai.py
│   │   ├── logs.py
│   │   ├── settings.py
│   │   ├── dashboard.py
│   │   ├── facebook.py
│   │   └── automation.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── products.html
│   │   ├── posts.html
│   │   ├── studio.html
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
│           ├── logs.js
│           └── settings.js
├── data/
│   └── .gitkeep
├── logs/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── README.md
```
