import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Article, Source

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_class=HTMLResponse)
async def health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    # Check Ollama / cloud LLM
    ollama_status = "n/a"
    if settings.LLM_PROVIDER == "ollama":
        ollama_status = "offline"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if resp.status_code == 200:
                    ollama_status = "online"
        except Exception:
            pass

    # Check DB
    db_status = "ok"
    articles_total = 0
    articles_done = 0
    articles_pending = 0
    articles_failed = 0
    try:
        articles_total = (
            await db.execute(select(func.count(Article.id)))
        ).scalar_one()
        articles_done = (
            await db.execute(
                select(func.count(Article.id)).where(Article.summary_status == "done")
            )
        ).scalar_one()
        articles_pending = (
            await db.execute(
                select(func.count(Article.id)).where(Article.summary_status == "pending")
            )
        ).scalar_one()
        articles_failed = (
            await db.execute(
                select(func.count(Article.id)).where(Article.summary_status == "failed")
            )
        ).scalar_one()
    except Exception:
        db_status = "error"

    # Scheduler state
    scheduler = getattr(request.app.state, "scheduler", None)
    scheduler_status = "running" if scheduler and scheduler.running else "stopped"

    # Last fetch time
    last_fetch = "never"
    try:
        row = (
            await db.execute(
                select(Source.last_fetched_at)
                .where(Source.last_fetched_at.isnot(None))
                .order_by(Source.last_fetched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row:
            last_fetch = row.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        pass

    overall_status = "ok"
    if ollama_status == "offline" or db_status == "error":
        overall_status = "degraded"

    ok_color    = "#3fb950"
    warn_color  = "#f0883e"
    err_color   = "#f85149"
    muted_color = "#8b949e"

    def sc(val, ok="ok", bad=None):
        if val == ok: return ok_color
        if bad and val == bad: return err_color
        return warn_color

    # Pre-compute colour tokens so f-string expressions need no string literals
    badge_bg     = "rgba(63,185,80,.15)" if overall_status == "ok" else "rgba(248,81,73,.15)"
    badge_color  = sc(overall_status, "ok", "degraded")
    sched_color  = sc(scheduler_status, "running", "stopped")
    ollama_color = sc(ollama_status, "online", "offline")
    db_color     = sc(db_status, "ok", "error")
    status_upper = overall_status.upper()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xybitz System Health</title>
  <style>
    :root {{
      --bg: #0d1117; --surf: #161b22; --border: #21262d;
      --text: #e6edf3; --muted: #8b949e; --acc: #6610f2;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; min-height: 100vh; }}
    .topbar {{ background: #010409; border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }}
    .brand {{ font-weight: 800; font-size: .9rem; letter-spacing: .08em; color: var(--text); text-decoration: none; }}
    .brand span {{ color: var(--acc); }}
    .tb-links {{ display: flex; gap: 8px; }}
    .tb-btn {{ color: var(--muted); text-decoration: none; font-size: .76rem; padding: 5px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surf); }}
    .tb-btn:hover {{ color: var(--text); }}
    .main {{ max-width: 700px; margin: 40px auto; padding: 0 20px 60px; }}
    h1 {{ font-size: 1.3rem; font-weight: 700; margin-bottom: 6px; }}
    .subtitle {{ color: var(--muted); font-size: .82rem; margin-bottom: 32px; }}
    .section {{ margin-bottom: 28px; }}
    .sec-label {{ font-size: .65rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #484f58; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: var(--surf); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 6px; font-size: .84rem; }}
    .row-label {{ color: var(--muted); }}
    .row-val {{ font-weight: 600; }}
    .stat-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
    .stat-box {{ background: var(--surf); border: 1px solid var(--border); border-radius: 8px; padding: 12px; text-align: center; }}
    .stat-num {{ font-size: 1.6rem; font-weight: 800; line-height: 1; }}
    .stat-lbl {{ font-size: .62rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin-top: 3px; }}
    .status-badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: .72rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
    .refresh-btn {{ margin-top: 24px; display: inline-block; padding: 8px 20px; background: rgba(102,16,242,.2); border: 1px solid rgba(102,16,242,.4); border-radius: 8px; color: #a78bfa; font-size: .82rem; text-decoration: none; font-weight: 600; cursor: pointer; }}
    .refresh-btn:hover {{ background: var(--acc); color: #fff; }}
  </style>
</head>
<body>
<div class="topbar">
  <a class="brand" href="/">🔐 XYBITZ <span>CONTROL</span></a>
  <div class="tb-links">
    <a class="tb-btn" href="/console">Console</a>
    <a class="tb-btn" href="/">← Site</a>
  </div>
</div>
<div class="main">
  <h1>System Health</h1>
  <p class="subtitle">Live system status — auto data from server</p>

  <div class="section">
    <div class="sec-label">Overall</div>
    <div class="row">
      <span class="row-label">System Status</span>
      <span class="status-badge" style="background:{badge_bg};color:{badge_color}">{status_upper}</span>
    </div>
    <div class="row">
      <span class="row-label">Scheduler</span>
      <span class="row-val" style="color:{sched_color}">{scheduler_status}</span>
    </div>
    <div class="row">
      <span class="row-label">Last Feed Fetch</span>
      <span class="row-val" style="color:{muted_color}">{last_fetch}</span>
    </div>
  </div>

  <div class="section">
    <div class="sec-label">AI / LLM</div>
    <div class="row">
      <span class="row-label">Provider</span>
      <span class="row-val" style="color:{muted_color}">{settings.LLM_PROVIDER}</span>
    </div>
    <div class="row">
      <span class="row-label">Ollama</span>
      <span class="row-val" style="color:{ollama_color}">{ollama_status}</span>
    </div>
    <div class="row">
      <span class="row-label">Model</span>
      <span class="row-val" style="color:{muted_color}">{settings.OLLAMA_MODEL}</span>
    </div>
  </div>

  <div class="section">
    <div class="sec-label">Database</div>
    <div class="row" style="margin-bottom:12px">
      <span class="row-label">DB Status</span>
      <span class="row-val" style="color:{db_color}">{db_status}</span>
    </div>
    <div class="stat-row">
      <div class="stat-box">
        <div class="stat-num" style="color:#e6edf3">{articles_total}</div>
        <div class="stat-lbl">Total</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" style="color:#3fb950">{articles_done}</div>
        <div class="stat-lbl">Done</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" style="color:#f0883e">{articles_pending}</div>
        <div class="stat-lbl">Pending</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" style="color:#f85149">{articles_failed}</div>
        <div class="stat-lbl">Failed</div>
      </div>
    </div>
  </div>

  <a class="refresh-btn" href="/health">↺ Refresh</a>
</div>
</body>
</html>"""

    return HTMLResponse(content=html)
