from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from telegram_auto_poster.utils.db import get_scheduled_posts
from telegram_auto_poster.utils.stats import stats

app = FastAPI(title="Telegram Autoposter Admin")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/queue", response_class=HTMLResponse)
async def queue(request: Request) -> HTMLResponse:
    raw_posts = get_scheduled_posts()
    posts = [
        (path, datetime.datetime.fromtimestamp(ts).isoformat())
        for path, ts in raw_posts
    ]
    context = {"request": request, "posts": posts}
    return templates.TemplateResponse("queue.html", context)


@app.get("/stats", response_class=HTMLResponse)
async def stats_view(request: Request) -> HTMLResponse:
    daily = await stats.get_daily_stats(reset_if_new_day=False)
    total = await stats.get_total_stats()
    perf = await stats.get_performance_metrics()
    approval_24h = await stats.get_approval_rate_24h(daily)
    approval_total = await stats.get_approval_rate_total()
    success_24h = await stats.get_success_rate_24h(daily)
    busiest_hour, busiest_count = await stats.get_busiest_hour()
    context = {
        "request": request,
        "daily": daily,
        "total": total,
        "perf": perf,
        "approval_24h": approval_24h,
        "approval_total": approval_total,
        "success_24h": success_24h,
        "busiest_hour": busiest_hour,
        "busiest_count": busiest_count,
    }
    return templates.TemplateResponse("stats.html", context)
