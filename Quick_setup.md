## Environment / configuration

You can provide configuration via environment variables or pass parameters programmatically.

- `APIFY_TOKEN` (required) — Apify API token used by `scraper.py`.
- `DB_PATH` (optional) — path to the SQLite file (default `facebook_posts.db`).
- `LOOKBACK_MINUTES` (optional) — not currently used by core code, but present for future use.
- `SCRAPE_LIMIT` (optional) — maximum number of posts to ask the actor for (default `5`).
- `OLLAMA_MODEL` (optional) — Ollama model to use (default `qwen3:latest`).
- `TELEGRAM_BOT_TOKEN` (optional) — Telegram bot token to use for notifications.
- `TELEGRAM_CHAT_ID` (optional) — Telegram chat ID to send notifications to.

Create a `.env` file in the `backend` directory:

```env
APIFY_TOKEN=your_apify_token_here
DB_PATH=facebook_posts.db
SCRAPE_LIMIT=5
OLLAMA_MODEL=qwen3:latest
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

### Custom Prompt

You can provide a custom prompt to the analyzer by modifying the `backend/prompt.md` file.

### Custom Groups

You can provide a custom list of groups to scrape by modifying the `backend/urls_to_scrape.json` file.

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
