# Xybitz

**CyberSec News · AI-Summarised · Always Current**

Xybitz is a production-grade cybersecurity news aggregator that fetches from 28 RSS sources across 8 categories, extracts full article bodies, and generates 50–60 word AI summaries using a local LLM (Ollama), OpenAI, or Groq — all with zero cost on the default stack.

---

## Quick Start

### 1. One-time setup (creates venv, installs deps, configures .env)

```bash
python setup.py
```

### 2. Run the app

```bash
make dev
```

Open `http://localhost:8000` in your browser.

---

## Features

- **28 RSS sources** across 8 security categories (threat intel, vulns, malware, appsec, cloud, compliance, privacy, AI security)
- **AI summaries** — 50–60 word summaries via Ollama (local), OpenAI, or Groq
- **HTMX-powered** category tabs and search — zero page reloads, zero custom JS
- **Admin panel** at `/admin` with full CRUD for articles, sources, and categories
- **Auto-ingestion** — fetches feeds on startup and every 30 minutes (configurable)
- **Deduplication** — SHA-256 URL hashing prevents duplicate articles
- **Smart categorisation** — keyword-based categoriser with priority ordering
- **Health endpoint** at `/health` — reports LLM, DB, scheduler, and article stats

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.115 + Jinja2 + HTMX 2.x |
| Database | SQLite (WAL mode) via SQLAlchemy 2.x async + aiosqlite |
| Scheduler | APScheduler 3.x (AsyncIOScheduler) |
| LLM | Ollama HTTP API / OpenAI API / Groq API (all via httpx) |
| Admin | sqladmin 0.19.0 |
| RSS parsing | feedparser |
| Content extraction | trafilatura |
| Config | pydantic-settings v2 |

---

## Configuration

All settings are read from `.env`. Copy `.env.example` and edit:

```env
LLM_PROVIDER=ollama          # ollama | openai | groq
OLLAMA_MODEL=llama3.2:3b     # any model pulled in Ollama
FETCH_INTERVAL_MINUTES=30
ARTICLE_RETENTION_DAYS=3
INITIAL_BACKFILL_DAYS=3
ADMIN_USERNAME=admin
ADMIN_PASSWORD=xybitz@admin
```

---

## Makefile Targets

| Command | Description |
|---|---|
| `make dev` | Start the dev server with hot-reload |
| `make setup` | Full environment setup (Python 3.12, venv, deps, Ollama) |
| `make test` | Run test suite |
| `make test-cov` | Run tests with HTML coverage report |
| `make lint` | Lint with ruff |
| `make format` | Format with ruff |
| `make db-reset` | Wipe the SQLite database |

---

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan, middleware
├── config.py            # pydantic-settings config
├── database.py          # Async SQLAlchemy engine + WAL pragma
├── models.py            # Article, Source, Category ORM models
├── schemas.py           # Pydantic response schemas
├── services/
│   ├── feed_ingestion.py   # RSS fetching + dedup + categorise
│   ├── deduplication.py    # SHA-256 URL hashing
│   ├── categoriser.py      # Keyword-based category classifier
│   ├── summariser.py       # LLM summarisation (Ollama/OpenAI/Groq)
│   └── scheduler.py        # APScheduler jobs
├── routers/
│   ├── articles.py      # GET / and GET /articles (HTMX-aware)
│   ├── categories.py    # GET /api/v1/categories
│   └── health.py        # GET /health
├── admin/
│   └── views.py         # sqladmin ModelViews + AdminAuth
└── templates/           # Jinja2 templates (base, index, detail, partials)
```

---

## Admin Panel

Navigate to `http://localhost:8000/admin` and log in with the credentials from your `.env`.

The admin provides full CRUD for:
- **Articles** — search, filter, export, toggle active/featured
- **Sources** — add/edit/delete RSS feeds
- **Categories** — manage display names and colors
