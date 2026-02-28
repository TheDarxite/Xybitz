import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqladmin import Admin
from sqlalchemy import select, update
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import AdminAuth, ArticleAdmin, CategoryAdmin, SourceAdmin
from app.config import settings
from app.database import AsyncSessionLocal, create_all_tables, engine, run_migrations
from app.models import Article, Category, Source
from app.routers.articles import router as articles_router
from app.routers.categories import router as categories_router
from app.routers.health import router as health_router
from app.routers.admin_actions import router as admin_actions_router
from app.services.scheduler import create_scheduler, ingest_and_summarise

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── STARTUP ──────────────────────────────────────────────────────────────
    await run_migrations()
    await create_all_tables()
    logger.info("Database tables ready")

    async with AsyncSessionLocal() as db:
        # Seed Category table if empty
        cat_result = await db.execute(select(Category))
        if not cat_result.scalars().first():
            seed_categories = [
                {"slug": "threat_intel",    "name": "Threat Intel",   "color": "purple"},
                {"slug": "vulnerabilities", "name": "Vulnerabilities", "color": "danger"},
                {"slug": "malware",         "name": "Malware",         "color": "warning"},
                {"slug": "appsec",          "name": "App Security",    "color": "primary"},
                {"slug": "cloud_security",  "name": "Cloud Security",  "color": "info"},
                {"slug": "compliance",      "name": "Compliance",      "color": "success"},
                {"slug": "privacy",         "name": "Privacy",         "color": "secondary"},
                {"slug": "ai_security",     "name": "AI Security",     "color": "#6610f2"},
            ]
            for cat in seed_categories:
                db.add(Category(**cat))
            await db.commit()
            logger.info("Categories seeded")

        # Seed Source table from feeds.yaml if empty
        src_result = await db.execute(select(Source))
        if not src_result.scalars().first():
            try:
                with open(settings.FEEDS_CONFIG_PATH, "r", encoding="utf-8") as fh:
                    feeds_config = yaml.safe_load(fh) or {}
                for feed in feeds_config.get("feeds", []):
                    db.add(
                        Source(
                            name=feed.get("name", ""),
                            url=feed.get("url", ""),
                            category=feed.get("category", "general"),
                            source_type=feed.get("type", "rss"),
                            scrape_engine=feed.get("scrape_engine"),
                            list_selector=feed.get("list_selector"),
                            link_selector=feed.get("link_selector"),
                            rate_limit_seconds=feed.get("rate_limit_seconds", 60),
                        )
                    )
                await db.commit()
                logger.info("Sources seeded from %s", settings.FEEDS_CONFIG_PATH)
            except Exception as exc:
                logger.error("Failed to seed sources: %s", exc)

    # ── Startup Recovery: reset stuck "processing" articles ──────────────
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Article)
            .where(Article.summary_status == "processing")
            .values(summary_status="pending")
        )
        await db.commit()
        if result.rowcount > 0:
            logger.warning(
                "Startup recovery: reset %d stuck 'processing' articles → 'pending'",
                result.rowcount,
            )

    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started")

    # Immediate fetch on startup — delayed 2s to let app fully init
    async def startup_task():
        await asyncio.sleep(2)
        logger.info("Starting initial ingest + summarise cycle...")
        await ingest_and_summarise()
        logger.info("Initial ingest + summarise cycle complete")

    asyncio.create_task(startup_task())
    logger.info("Initial ingest task queued")

    yield

    # ── SHUTDOWN ─────────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# ── Session middleware — MUST be added before routes that use request.session ──
app.add_middleware(SessionMiddleware, secret_key=settings.ADMIN_PASSWORD)

# ── /admin/ redirect — must be registered BEFORE sqladmin mount ───────────────
# After sqladmin login it redirects to /admin/; this intercepts that and sends
# authenticated users straight to the control center at /console.
@app.get("/admin/")
async def admin_home_redirect(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse("/console", status_code=302)
    return RedirectResponse("/admin/login", status_code=302)


_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xybitz — Sign In</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;}
.login-wrap{width:100%;max-width:380px;padding:24px;}
.login-card{background:#161b22;border:1px solid #21262d;border-radius:14px;padding:36px 32px;}
.brand{text-align:center;margin-bottom:28px;}
.brand-title{font-size:1.3rem;font-weight:800;letter-spacing:.1em;color:#e6edf3;}
.brand-title span{color:#6610f2;}
.brand-sub{font-size:.65rem;font-weight:700;letter-spacing:.14em;color:#6610f2;text-transform:uppercase;margin-top:3px;}
.lock-icon{font-size:2rem;margin-bottom:10px;display:block;filter:grayscale(.3);}
.form-group{margin-bottom:14px;}
.form-group label{display:block;font-size:.72rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#8b949e;margin-bottom:5px;}
.form-group input{width:100%;background:#1c2128;border:1px solid #21262d;color:#e6edf3;border-radius:8px;padding:10px 13px;font-size:.9rem;outline:none;transition:border-color .15s;}
.form-group input:focus{border-color:#6610f2;}
.btn-sign-in{width:100%;background:#6610f2;border:none;color:#fff;font-size:.88rem;font-weight:700;padding:11px;border-radius:8px;cursor:pointer;margin-top:6px;letter-spacing:.04em;transition:background .15s;}
.btn-sign-in:hover{background:#7c3aed;}
.error-msg{background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.4);color:#f85149;border-radius:8px;padding:10px 13px;font-size:.8rem;margin-bottom:16px;text-align:center;}
.footer-note{text-align:center;color:#484f58;font-size:.68rem;margin-top:20px;}
</style>
</head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <div class="brand">
      <span class="lock-icon">🔐</span>
      <div class="brand-title">XYBITZ <span>CONTROL</span></div>
      <div class="brand-sub">Pipeline Management Console</div>
    </div>
    {error_block}
    <form method="post" action="/admin/login">
      <div class="form-group">
        <label>Username</label>
        <input type="text" name="username" autocomplete="username" autofocus placeholder="admin">
      </div>
      <div class="form-group">
        <label>Password</label>
        <input type="password" name="password" autocomplete="current-password" placeholder="••••••••">
      </div>
      <button type="submit" class="btn-sign-in">Sign In</button>
    </form>
  </div>
  <div class="footer-note">Xybitz Cybersecurity Aggregator</div>
</div>
</body>
</html>"""

_LOGIN_ERROR_BLOCK = '<div class="error-msg">Invalid credentials — try again.</div>'


@app.get("/admin/login")
async def admin_login_page(request: Request):
    """Serve the dark-themed custom login page before sqladmin handles the POST."""
    if request.session.get("authenticated"):
        return RedirectResponse("/console", status_code=302)
    error = request.query_params.get("error")
    error_block = _LOGIN_ERROR_BLOCK if error else ""
    html = _LOGIN_PAGE.replace("{error_block}", error_block)
    return HTMLResponse(html)


# ── Admin action routes — MUST be before Admin(app,...) mount ─────────────────
# sqladmin mounts at /admin and intercepts ALL /admin/* in route-order priority.
# Registering these routes first ensures FastAPI handles them, not sqladmin.
app.include_router(admin_actions_router)

# ── Admin ─────────────────────────────────────────────────────────────────────
auth_backend = AdminAuth(secret_key=settings.ADMIN_PASSWORD)
admin = Admin(app, engine, authentication_backend=auth_backend, base_url="/admin")
admin.add_view(ArticleAdmin)
admin.add_view(SourceAdmin)
admin.add_view(CategoryAdmin)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(articles_router)
app.include_router(categories_router, prefix="/api/v1")
app.include_router(health_router)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d [%.1fms]",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ── Global 500 handler ────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse({"error": str(exc), "status": 500}, status_code=500)


# ── Admin dashboard ───────────────────────────────────────────────────────────
@app.get("/console")
async def admin_console(request: Request):
    if not request.session.get("authenticated"):
        return RedirectResponse("/admin/login")
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})
