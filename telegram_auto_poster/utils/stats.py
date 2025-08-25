"""Asynchronous statistics module backed solely by Valkey (Redis)."""

from __future__ import annotations

import asyncio
import datetime
from typing import Optional

from telegram_auto_poster.utils.db import (
    _redis_key,
    _redis_meta_key,
    get_async_redis_client,
)
from telegram_auto_poster.utils.timezone import now_utc


class MediaStats:
    """Collect and retrieve runtime statistics using Valkey only."""

    _instance: "MediaStats" | None = None

    def __new__(cls) -> "MediaStats":  # pragma: no cover - singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.r = get_async_redis_client()
            cls._instance.names = [
                "media_received",
                "media_processed",
                "photos_received",
                "videos_received",
                "photos_processed",
                "videos_processed",
                "photos_approved",
                "videos_approved",
                "photos_rejected",
                "videos_rejected",
                "photos_added_to_batch",
                "videos_added_to_batch",
                "batch_sent",
                "processing_errors",
                "storage_errors",
                "telegram_errors",
                "list_operations",
                "client_reconnects",
                "rate_limit_drops",
            ]
            try:  # Initialise counters immediately
                loop = asyncio.get_running_loop()
                loop.create_task(cls._instance._init())
            except RuntimeError:  # no running loop
                asyncio.run(cls._instance._init())
        return cls._instance

    async def _init(self) -> None:
        for scope in ("daily", "total"):
            for name in self.names:
                await self.r.setnx(_redis_key(scope, name), 0)
        await self.r.setnx(_redis_meta_key(), now_utc().isoformat())

    async def _increment(self, name: str, scope: str = "daily", count: int = 1) -> None:
        await self.r.incrby(_redis_key(scope, name), count)

    async def _record_duration(self, base: str, duration: float) -> None:
        await self.r.incrbyfloat(_redis_key("perf", f"{base}_total"), duration)
        await self.r.incrby(_redis_key("perf", f"{base}_count"), 1)

    async def record_received(self, media_type: str) -> None:
        await self._increment("media_received")
        await self._increment("media_received", scope="total")
        if media_type == "photo":
            await self._increment("photos_received")
            await self._increment("photos_received", scope="total")
        elif media_type == "video":
            await self._increment("videos_received")
            await self._increment("videos_received", scope="total")

    async def record_processed(self, media_type: str, processing_time: float) -> None:
        await self._increment("media_processed")
        await self._increment("media_processed", scope="total")
        await self._record_duration(f"{media_type}_processing", processing_time)
        if media_type == "photo":
            await self._increment("photos_processed")
            await self._increment("photos_processed", scope="total")
        elif media_type == "video":
            await self._increment("videos_processed")
            await self._increment("videos_processed", scope="total")

    async def record_approved(
        self, media_type: str, filename: str | None = None, source: str | None = None
    ) -> None:
        name = "photos_approved" if media_type == "photo" else "videos_approved"
        await self._increment(name)
        await self._increment(name, scope="total")
        hour_key = _redis_key("hourly", str(now_utc().hour))
        await self.r.incrby(hour_key, 1)

    async def record_rejected(
        self, media_type: str, filename: str | None = None, source: str | None = None
    ) -> None:
        name = "photos_rejected" if media_type == "photo" else "videos_rejected"
        await self._increment(name)
        await self._increment(name, scope="total")
        hour_key = _redis_key("hourly", str(now_utc().hour))
        await self.r.incrby(hour_key, 1)

    async def record_added_to_batch(self, media_type: str) -> None:
        name = (
            "photos_added_to_batch"
            if media_type == "photo"
            else "videos_added_to_batch"
        )
        await self._increment(name)
        await self._increment(name, scope="total")

    async def record_batch_sent(self, count: int) -> None:
        await self._increment("batch_sent", count=count)
        await self._increment("batch_sent", scope="total", count=count)

    async def record_client_reconnect(self) -> None:
        await self._increment("client_reconnects")
        await self._increment("client_reconnects", scope="total")

    async def record_rate_limit_drop(self) -> None:
        await self._increment("rate_limit_drops")
        await self._increment("rate_limit_drops", scope="total")

    async def record_error(self, error_type: str, error_message: str) -> None:
        if error_type == "processing":
            name = "processing_errors"
        elif error_type == "storage":
            name = "storage_errors"
        else:
            name = "telegram_errors"
        await self._increment(name)
        await self._increment(name, scope="total")

    async def record_storage_operation(
        self, operation_type: str, duration: float
    ) -> None:
        if operation_type not in ("upload", "download", "list"):
            return
        await self._record_duration(operation_type, duration)
        if operation_type == "list":
            await self._increment("list_operations")
            await self._increment("list_operations", scope="total")

    async def get_daily_stats(self, reset_if_new_day: bool = True) -> dict:
        last_reset_raw = await self.r.get(_redis_meta_key())
        last_reset = (
            datetime.datetime.fromisoformat(last_reset_raw)
            if last_reset_raw
            else now_utc()
        )
        now = now_utc()
        if reset_if_new_day and last_reset.date() < now.date():
            await self.reset_daily_stats()
            last_reset = now
        stats: dict[str, int | str] = {}
        for name in self.names:
            value = await self.r.get(_redis_key("daily", name)) or 0
            stats[name] = int(value)
        stats["last_reset"] = last_reset.isoformat()
        return stats

    async def get_total_stats(self) -> dict:
        stats: dict[str, int] = {}
        for name in self.names:
            value = await self.r.get(_redis_key("total", name)) or 0
            stats[name] = int(value)
        return stats

    async def _avg(self, base: str) -> float:
        total = await self.r.get(_redis_key("perf", f"{base}_total")) or 0
        count = await self.r.get(_redis_key("perf", f"{base}_count")) or 0
        return float(total) / int(count) if int(count) else 0.0

    async def get_performance_metrics(self) -> dict:
        return {
            "avg_photo_processing_time": await self._avg("photo_processing"),
            "avg_video_processing_time": await self._avg("video_processing"),
            "avg_upload_time": await self._avg("upload"),
            "avg_download_time": await self._avg("download"),
        }

    async def get_approval_rate_24h(self, daily: dict) -> float:
        processed = daily["photos_processed"] + daily["videos_processed"]
        approved = daily["photos_approved"] + daily["videos_approved"]
        return (approved / processed * 100) if processed else 0.0

    async def get_approval_rate_total(self) -> float:
        ts = await self.get_total_stats()
        processed = ts["photos_processed"] + ts["videos_processed"]
        approved = ts["photos_approved"] + ts["videos_approved"]
        return (approved / processed * 100) if processed else 0.0

    async def get_success_rate_24h(self, daily: dict) -> float:
        received = daily["media_received"]
        errors = (
            daily["processing_errors"]
            + daily["storage_errors"]
            + daily["telegram_errors"]
        )
        return ((received - errors) / received * 100) if received else 100.0

    async def get_busiest_hour(self) -> tuple[Optional[int], int]:
        max_count = 0
        max_hour: Optional[int] = None
        for hour in range(24):
            count = int(await self.r.get(_redis_key("hourly", str(hour))) or 0)
            if count > max_count:
                max_count = count
                max_hour = hour
        return max_hour, max_count

    async def generate_stats_report(self, reset_daily: bool = True) -> str:
        daily = await self.get_daily_stats(reset_if_new_day=reset_daily)
        total = await self.get_total_stats()
        perf = await self.get_performance_metrics()
        approval_24h = await self.get_approval_rate_24h(daily)
        approval_total = await self.get_approval_rate_total()
        success_24h = await self.get_success_rate_24h(daily)
        errors_24h = (
            daily.get("processing_errors", 0)
            + daily.get("storage_errors", 0)
            + daily.get("telegram_errors", 0)
        )
        errors_total = (
            total.get("processing_errors", 0)
            + total.get("storage_errors", 0)
            + total.get("telegram_errors", 0)
        )
        busiest_hour, count = await self.get_busiest_hour()
        busiest_display = (
            f"{busiest_hour}:00-{busiest_hour + 1}:00"
            if busiest_hour is not None
            else "N/A"
        )

        def fmt(icon: str, title: str, value: object, extra: str = "") -> str:
            return f"{icon} <b>{title}:</b> {value} {extra}".strip()

        report_sections = {
            "header": "📊 <b>Statistics Report</b> 📊\n",
            "daily": [
                "<b>Last 24 Hours:</b>\n",
                fmt("📥", "Media Received", daily.get("media_received", 0)),
                fmt("🖼️", "Photos Processed", daily.get("photos_processed", 0)),
                fmt("📹", "Videos Processed", daily.get("videos_processed", 0)),
                fmt(
                    "✅",
                    "Approved",
                    f"{daily.get('photos_approved', 0)} photos, {daily.get('videos_approved', 0)} videos",
                ),
                fmt(
                    "❌",
                    "Rejected",
                    f"{daily.get('photos_rejected', 0)} photos, {daily.get('videos_rejected', 0)} videos",
                ),
                fmt("📦", "Batches Sent", daily.get("batch_sent", 0)),
                fmt("📈", "Approval Rate", f"{approval_24h:.1f}%"),
                fmt("✨", "Success Rate", f"{success_24h:.1f}%"),
                fmt("🛑", "Errors", errors_24h),
                fmt("🕔", "Busiest Hour", busiest_display, f"({count} events)"),
            ],
            "performance": [
                "\n<b>Performance Metrics:</b>\n",
                fmt(
                    "🖼️",
                    "Avg Photo Processing",
                    f"{perf['avg_photo_processing_time']:.2f}s",
                ),
                fmt(
                    "📹",
                    "Avg Video Processing",
                    f"{perf['avg_video_processing_time']:.2f}s",
                ),
                fmt("⬆️", "Avg Upload", f"{perf['avg_upload_time']:.2f}s"),
                fmt("⬇️", "Avg Download", f"{perf['avg_download_time']:.2f}s"),
            ],
            "total": [
                "\n<b>All-Time Totals:</b>\n",
                fmt("🖼️", "Photos Processed", total.get("photos_processed", 0)),
                fmt("📹", "Videos Processed", total.get("videos_processed", 0)),
                fmt(
                    "✅",
                    "Approved",
                    f"{total.get('photos_approved', 0)} photos, {total.get('videos_approved', 0)} videos",
                ),
                fmt(
                    "❌",
                    "Rejected",
                    f"{total.get('photos_rejected', 0)} photos, {total.get('videos_rejected', 0)} videos",
                ),
                fmt("📦", "Batches Sent", total.get("batch_sent", 0)),
                fmt("📈", "Approval Rate", f"{approval_total:.1f}%"),
                fmt("🛑", "Errors", errors_total),
                fmt("🗃️", "List Operations", total.get("list_operations", 0)),
            ],
            "footer": [f"\n<i>Last reset: {daily.get('last_reset')}</i>"],
        }

        return "\n".join(
            [
                report_sections["header"],
                "\n".join(report_sections["daily"]),
                "\n".join(report_sections["performance"]),
                "\n".join(report_sections["total"]),
                "\n".join(report_sections["footer"]),
            ]
        )

    async def reset_daily_stats(self) -> str:
        for name in self.names:
            await self.r.set(_redis_key("daily", name), 0)
        now = now_utc().isoformat()
        await self.r.set(_redis_meta_key(), now)
        for hour in range(24):
            await self.r.delete(_redis_key("hourly", str(hour)))
        return "Daily statistics have been reset."

    async def force_save(self) -> None:
        try:
            await self.r.save()
        except Exception:
            pass


stats = MediaStats()
