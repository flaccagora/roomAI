# Facebook group scraping → DB → analysis pipeline

This repository contains a small pipeline that scrapes Facebook group posts (via an Apify actor), saves raw posts into a local SQLite database, analyzes the post text with a local LLM (expected on http://localhost:11434), and promotes accepted posts into a `good_facebook_posts` table.

It also includes a small FastAPI-based server that can run the pipeline at configurable intervals and notify you (via webhook or logs) when new accepted posts are found.

## Project layout

- `scraper.py` — lightweight wrapper around `apify-client` to run an Apify actor and collect dataset items.
- `analyzer.py` — sends post text to a local Ollama-like LLM and expects a JSON response indicating `ACCETTATO` or `SCARTATO`.
- `database.py` — SQLite wrapper that creates `facebook_posts` and `good_facebook_posts` tables and inserts scraped rows.
- `run_pipeline.py` — orchestrator: exposes `run_pipeline(...)` for one-off runs and has a CLI entrypoint.
- `server.py` — FastAPI app that schedules runs (APScheduler) and optionally notifies a webhook when new accepted posts are found.
- `requirements.txt` — recommended Python package pins.

## Requirements

- Python 3.10+ (tested on Linux)
- An Apify account and an Apify token (for the actor used in `scraper.py`).
- A local LLM compatible with the analyzer (by default the analyzer posts to `http://localhost:11434/api/generate`).
- Network access to Apify and to the webhook target if using notifications.

## Environment / configuration

You can provide configuration via environment variables or pass parameters programmatically.

- `APIFY_TOKEN` (required) — Apify API token used by `scraper.py`.
- `DB_PATH` (optional) — path to the SQLite file (default `facebook_posts.db`).
- `LOOKBACK_MINUTES` (optional) — not currently used by core code, but present for future use.
- `SCRAPE_LIMIT` (optional) — maximum number of posts to ask the actor for (default `5`).
- `OLLAMA_MODEL` (optional) — Ollama model to use (default `qwen3:latest`).
- `TELEGRAM_BOT_TOKEN` (optional) — Telegram bot token to use for notifications.
- `TELEGRAM_CHAT_ID` (optional) — Telegram chat ID to send notifications to.

Create a `.env` file in the `backend` directory for convenience (works with `python-dotenv`):

```env
APIFY_TOKEN=your_apify_token_here
DB_PATH=facebook_posts.db
SCRAPE_LIMIT=5
OLLAMA_MODEL=qwen3:latest
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
SCRAPE_TYPE=group or post
SCRAPE_QUERY="search query" // inactive if SCRAPE_TYPE=group
```

### Custom Prompt

You can provide a custom prompt to the analyzer by modifying the `backend/prompt.md` file.

### Custom Groups

You can provide a custom list of groups to scrape by modifying the `backend/urls_to_scrape.json` file.

## Install

Install the Python dependencies into your environment. From the repo root:

```bash
python3 -m pip install -r requirements.txt
```

Note: if you prefer a virtualenv or conda environment, create and activate it first.

## Run the pipeline manually

To run one pipeline iteration from the command line:

```bash
python3 run_pipeline.py
```

Or import and call `run_pipeline.run_pipeline()` from Python:

```python
from run_pipeline import run_pipeline
accepted = run_pipeline()
print('Accepted items:', len(accepted))
```

The function returns a list of accepted items (those the analyzer marked as `ACCETTATO`) and will insert scraped rows into `facebook_posts` and accepted ones into `good_facebook_posts`.

## Run the server (schedule + notifications)

Start the FastAPI server (from the project root):

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

API endpoints

- POST /start_every?minutes=30 — start a periodic job that runs every `minutes`. JSON body (optional): `{ "webhook": "https://example.com/hook" }` to receive a POST when new accepted posts are found.
- POST /run_now — trigger a one-off run in background. Optional JSON body: `{ "webhook": "https://example.com/hook" }`.
- GET /status — returns scheduled job ids.

Examples (curl):

```bash
# Schedule to run every 15 minutes and notify webhook
curl -X POST "http://localhost:8000/start_every?minutes=15" -H "Content-Type: application/json" -d '{"webhook":"https://example.com/hook"}'

# Run once now (background)
curl -X POST "http://localhost:8000/run_now" -H "Content-Type: application/json" -d '{}'

# Check scheduler status
curl http://localhost:8000/status
```

## Run with Docker

Prerequisites

- Docker and Docker Compose installed
- A local LLM (Ollama) running on the host at `http://localhost:11434` (the analyzer in `backend/analyzer.py` calls this URL)
- Environment values in `backend/.env` (e.g., `APIFY_TOKEN`, `SCRAPE_LIMIT`, `LOOKBACK_MINUTES`). `DB_PATH` is overridden to `/data/facebook_posts.db` inside the container for persistence.

Build and start

```bash
docker compose up --build
```

Access

- App: http://localhost:8000/
- OpenAPI docs: http://localhost:8000/docs

Persistence

- SQLite data is stored in a named Docker volume `apify_data` mounted at `/data` in the container.
- To remove data: list the volume and remove it explicitly, e.g.

```bash
docker volume ls | grep apify_data
docker volume rm <volume_name>
```

Operational commands

```bash
# Stop containers (keeps the volume/data)
docker compose down

# Tail logs
docker compose logs -f
```

Notes

- The Compose file uses `network_mode: host` so the container can reach the host’s Ollama at `localhost:11434`.
- If you cannot use host networking, expose ports instead and update the analyzer to use an env like `OLLAMA_URL` (or `http://host.docker.internal:11434` where supported), then remove `network_mode: host` and add `ports: ["8000:8000"]`.

## Notification behavior

- When a run produces accepted posts, the server will check their `id` against an in-memory set of previously-notified IDs and only notify for unseen ones.
- Notification payload (JSON) format posted to the webhook:

```json
{
  "new_good_count": 2,
  "ids": ["postid1", "postid2"],
  "samples": ["first 200 chars of text", "..."]
}
```

If no webhook is provided, notifications are logged.

Important: the in-memory `LAST_SEEN_IDS` is not persisted. On server restart, notifications may be re-sent for previously accepted rows. See "Persistence" below for how to change that.

## Persistence and improving notifications

Currently `server.py` keeps a runtime-only set of notified IDs. To avoid duplicate notifications across restarts, update the server to initialize `LAST_SEEN_IDS` from the DB at startup:

- Query the `good_facebook_posts` table for `id` values and populate `LAST_SEEN_IDS`.
- I can implement this change for you if you want.

## Troubleshooting

- ModuleNotFoundError: fastapi — install requirements with `pip install -r requirements.txt`.
- RuntimeError: Apify token not provided — set `APIFY_TOKEN` in environment or `.env`.
- Analyzer/LLM errors — ensure a compatible LLM is running at `http://localhost:11434` (the analyzer posts to `/api/generate`). If you don't run a local model, you can modify `analyzer.py` to use another LLM provider (OpenAI, etc.).
- Actor / dataset changes — `scraper.py` calls a specific Apify actor id; if the actor changes, update the actor id string in `scraper.py`.

If you see exceptions logged per-item during analysis, the pipeline continues to process other items; inspect logs to see which items failed and why.

## Security & production notes

- If exposing `server.py` publicly, add authentication and rate-limiting to the endpoints.
- Secure your webhook endpoint and ensure it's reachable from the server host.
- Consider moving `LAST_SEEN_IDS` persistence into the DB or using a lightweight key-value store (Redis) for production.

## Next steps / optional enhancements

- Persist `LAST_SEEN_IDS` from DB at startup (prevents duplicate notifications on restart).
- Add email/Telegram/Slack notification adapters.
- Add retries and backoff for network calls (Apify, webhook, analyzer).
- Add unit tests for `database.py`, `scraper.py` (mock Apify), and `analyzer.py` (mock LLM response).

## Contact / help

If you want, I can:

- Wire persistent `LAST_SEEN_IDS` from the DB into `server.py`.
- Add an example `.env.example` file and a small test harness to run the pipeline against a mocked dataset.

---

Minimal reproduction and quick checks

```bash
# show python version
python3 --version

# install deps
python3 -m pip install -r requirements.txt

# run one pipeline iteration
python3 run_pipeline.py

# start server
uvicorn server:app --reload
```
