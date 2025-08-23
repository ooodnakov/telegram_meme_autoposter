from __future__ import annotations

import asyncio
import datetime
import mimetypes
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from telegram_auto_poster.config import BUCKET_MAIN, CONFIG
from telegram_auto_poster.utils.db import get_scheduled_posts, remove_scheduled_post
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage

app = FastAPI(title="Telegram Autoposter Admin")

base_path = Path(__file__).parent
templates = Jinja2Templates(directory=str(base_path / "templates"))
app.mount("/static", StaticFiles(directory=str(base_path / "static")), name="static")


def require_access_key(request: Request) -> None:
    access_key = CONFIG.web.access_key
    if access_key is None:
        return
    provided = request.query_params.get("key")
    expected = access_key.get_secret_value()
    if not (provided and secrets.compare_digest(provided, expected)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access key"
        )


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_access_key)])
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get(
    "/queue",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_key)],
)
async def queue(request: Request) -> HTMLResponse:
    raw_posts = await run_in_threadpool(get_scheduled_posts)
    posts: list[dict] = []
    for path, ts in raw_posts:
        url = await storage.get_presigned_url(path)
        if not url:
            continue

        # Derive media information for proper embedding in template
        mime, _ = mimetypes.guess_type(path)
        is_video = path.startswith("videos/") or (mime or "").startswith("video/")
        is_image = path.startswith("photos/") or (mime or "").startswith("image/")

        posts.append(
            {
                "path": path,
                "ts": datetime.datetime.fromtimestamp(ts).isoformat(),
                "url": url,
                "mime": mime or ("video/mp4" if is_video else None),
                "is_video": is_video,
                "is_image": is_image,
            }
        )

    context = {"request": request, "posts": posts}
    return templates.TemplateResponse("queue.html", context)


@app.post("/queue/unschedule")
async def unschedule(path: str = Form(...)) -> RedirectResponse:
    await run_in_threadpool(remove_scheduled_post, path)
    try:
        if await storage.file_exists(path, BUCKET_MAIN):
            await storage.delete_file(path, BUCKET_MAIN)
    except Exception:
        # Best-effort delete; still redirect to keep UX smooth
        pass
    return RedirectResponse(url="/queue", status_code=303)


@app.get(
    "/stats",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_key)],
)
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
