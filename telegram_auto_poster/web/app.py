from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
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
    raw_posts = await run_in_threadpool(get_scheduled_posts)
    posts = [
        (path, datetime.datetime.fromtimestamp(ts).isoformat())
        for path, ts in raw_posts
    ]
    context = {"request": request, "posts": posts}
    return templates.TemplateResponse("queue.html", context)


@app.get("/stats", response_class=HTMLResponse)
async def stats_view(request: Request) -> HTMLResponse:
    daily, total, perf, busiest = await asyncio.gather(
        stats.get_daily_stats(reset_if_new_day=False),
        stats.get_total_stats(),
        stats.get_performance_metrics(),
        stats.get_busiest_hour(),
    )
    busiest_hour, busiest_count = busiest
    approval_24h, approval_total, success_24h = await asyncio.gather(
        stats.get_approval_rate_24h(daily),
        stats.get_approval_rate_total(),
        stats.get_success_rate_24h(daily),
    )
    daily_errors = (
        daily["processing_errors"] + daily["storage_errors"] + daily["telegram_errors"]
    )
    total_errors = (
        total["processing_errors"] + total["storage_errors"] + total["telegram_errors"]
    )
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
        "daily_errors": daily_errors,
        "total_errors": total_errors,
    }
    return templates.TemplateResponse("stats.html", context)
