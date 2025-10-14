"""Asynchronous statistics module backed solely by Valkey (Redis)."""

from __future__ import annotations

import asyncio
import datetime
import heapq
from typing import Optional

from telegram_auto_poster.utils.db import (
    AsyncValkeyClient,
    _redis_key,
    _redis_meta_key,
    get_async_redis_client,
)
from telegram_auto_poster.utils.timezone import now_utc


class MediaStats:
    """Collect and retrieve runtime statistics using Valkey only."""

    r: AsyncValkeyClient
    """Connected async Valkey client used for all operations."""

    names: list[str]
    """List of metric names that are tracked in Valkey."""

    _instance: "MediaStats" | None = None

    processing_histogram_bounds: tuple[float, ...]
    """Upper bounds (seconds) for processing time histogram buckets."""

    processing_histogram_labels: tuple[str, ...]
    """Human friendly labels for :attr:`processing_histogram_bounds`."""

    def __new__(cls) -> "MediaStats":  # pragma: no cover - singleton
        """Create or return the singleton instance."""
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
            cls._instance.processing_histogram_bounds = (1.0, 2.0, 5.0, 10.0)
            cls._instance.processing_histogram_labels = (
                "<1s",
                "1-2s",
                "2-5s",
                "5-10s",
                "≥10s",
            )
            try:  # Initialise counters immediately
                loop = asyncio.get_running_loop()
                loop.create_task(cls._instance._init())
            except RuntimeError:  # no running loop
                asyncio.run(cls._instance._init())
        return cls._instance

    async def _init(self) -> None:
        """Initialise counters in Valkey if they do not exist."""
        for scope in ("daily", "total"):
            for name in self.names:
                await self.r.setnx(_redis_key(scope, name), 0)
        await self.r.setnx(_redis_meta_key(), now_utc().isoformat())

    async def _increment(self, name: str, scope: str = "daily", count: int = 1) -> None:
        """Increase a counter for ``name`` by ``count`` within ``scope``."""
        await self.r.incrby(_redis_key(scope, name), count)

    async def _record_duration(self, base: str, duration: float) -> None:
        """Record a timing metric for ``base`` measured in seconds."""
        await self.r.incrbyfloat(_redis_key("perf", f"{base}_total"), duration)
        await self.r.incrby(_redis_key("perf", f"{base}_count"), 1)

    async def record_submission(self, source: str) -> None:
        """Increase the submission count for ``source``."""
        if source:
            key = _redis_key("leaderboard", "submissions")
            await self.r.zincrby(key, 1, source)
            await self.r.persist(key)

    async def record_received(self, media_type: str) -> None:
        """Record that a piece of media of ``media_type`` was received."""
        await self._increment("media_received")
        await self._increment("media_received", scope="total")
        if media_type == "photo":
            await self._increment("photos_received")
            await self._increment("photos_received", scope="total")
        elif media_type == "video":
            await self._increment("videos_received")
            await self._increment("videos_received", scope="total")

    async def record_processed(self, media_type: str, processing_time: float) -> None:
        """Record that media was processed and log its duration."""
        await self._increment("media_processed")
        await self._increment("media_processed", scope="total")
        await self._record_duration(f"{media_type}_processing", processing_time)
        await self._record_processing_histogram(media_type, processing_time)
        if media_type == "photo":
            await self._increment("photos_processed")
            await self._increment("photos_processed", scope="total")
        elif media_type == "video":
            await self._increment("videos_processed")
            await self._increment("videos_processed", scope="total")

    async def record_approved(
        self,
        media_type: str,
        filename: str | None = None,
        source: str | None = None,
        count: int = 1,
    ) -> None:
        """Record that an item was approved for publication."""
        name = "photos_approved" if media_type == "photo" else "videos_approved"
        await self._increment(name, count=count)
        await self._increment(name, scope="total", count=count)
        hour_key = _redis_key("hourly", str(now_utc().hour))
        await self.r.incrby(hour_key, count)
        await self.r.persist(hour_key)
        if source:
            appr_key = _redis_key("leaderboard", "approved")
            await self.r.zincrby(appr_key, count, source)
            await self.r.persist(appr_key)

    async def record_post_published(
        self, count: int = 1, *, timestamp: datetime.datetime | None = None
    ) -> None:
        """Record that ``count`` posts were published to the target channels."""

        ts = timestamp or now_utc()
        day_key = ts.strftime("%Y-%m-%d")
        await self.r.incrby(_redis_key("posts", day_key), count)

    async def record_rejected(
        self, media_type: str, filename: str | None = None, source: str | None = None
    ) -> None:
        """Record that an item was rejected."""
        name = "photos_rejected" if media_type == "photo" else "videos_rejected"
        await self._increment(name)
        await self._increment(name, scope="total")
        hour_key = _redis_key("hourly", str(now_utc().hour))
        await self.r.incrby(hour_key, 1)
        await self.r.persist(hour_key)
        if source:
            rej_key = _redis_key("leaderboard", "rejected")
            await self.r.zincrby(rej_key, 1, source)
            await self.r.persist(rej_key)

    async def record_added_to_batch(self, media_type: str) -> None:
        """Record that media was added to the batch queue."""
        name = (
            "photos_added_to_batch"
            if media_type == "photo"
            else "videos_added_to_batch"
        )
        await self._increment(name)
        await self._increment(name, scope="total")

    async def record_batch_sent(self, count: int) -> None:
        """Record that a batch of ``count`` items was sent."""
        await self._increment("batch_sent", count=count)
        await self._increment("batch_sent", scope="total", count=count)

    async def record_client_reconnect(self) -> None:
        """Record that the Telegram client reconnected."""
        await self._increment("client_reconnects")
        await self._increment("client_reconnects", scope="total")

    async def record_rate_limit_drop(self) -> None:
        """Record that an update was dropped due to rate limiting."""
        await self._increment("rate_limit_drops")
        await self._increment("rate_limit_drops", scope="total")

    async def record_error(self, error_type: str, error_message: str) -> None:
        """Record an error occurrence by ``error_type``."""
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
        """Record timing and counts for storage operations."""
        if operation_type not in ("upload", "download", "list"):
            return
        await self._record_duration(operation_type, duration)
        if operation_type == "list":
            await self._increment("list_operations")
            await self._increment("list_operations", scope="total")

    async def get_daily_stats(
        self, reset_if_new_day: bool = True
    ) -> dict[str, int | str]:
        """Return daily statistics, resetting if a new day has begun."""
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

    async def get_total_stats(self) -> dict[str, int]:
        """Return all-time statistics."""
        stats: dict[str, int] = {}
        for name in self.names:
            value = await self.r.get(_redis_key("total", name)) or 0
            stats[name] = int(value)
        return stats

    async def get_daily_post_counts(self, days: int = 14) -> list[dict[str, str | int]]:
        """Return the number of posts published per day for the last ``days`` days."""

        today = now_utc().date()
        start = today - datetime.timedelta(days=days - 1)
        dates = [start + datetime.timedelta(days=i) for i in range(days)]
        keys = [_redis_key("posts", d.strftime("%Y-%m-%d")) for d in dates]
        if keys:
            raw_values = await self.r.mget(*keys)
        else:  # pragma: no cover - empty range safeguard
            raw_values = []
        results: list[dict[str, str | int]] = []
        for date_obj, value in zip(dates, raw_values):
            count = int(value) if value else 0
            results.append({"date": date_obj.isoformat(), "count": count})
        return results

    async def _avg(self, base: str) -> float:
        """Return the average duration recorded for ``base``."""
        total = await self.r.get(_redis_key("perf", f"{base}_total")) or 0
        count = await self.r.get(_redis_key("perf", f"{base}_count")) or 0
        return float(total) / int(count) if int(count) else 0.0

    async def get_performance_metrics(self) -> dict[str, float]:
        """Return average processing and transfer times in seconds."""
        return {
            "avg_photo_processing_time": await self._avg("photo_processing"),
            "avg_video_processing_time": await self._avg("video_processing"),
            "avg_upload_time": await self._avg("upload"),
            "avg_download_time": await self._avg("download"),
        }

    async def get_approval_rate_24h(self, daily: dict[str, int | str]) -> float:
        """Return approval percentage for the last 24 hours."""
        processed = int(daily["photos_processed"]) + int(daily["videos_processed"])
        approved = int(daily["photos_approved"]) + int(daily["videos_approved"])
        return (approved / processed * 100) if processed else 0.0

    async def get_approval_rate_total(self) -> float:
        """Return the all-time approval percentage."""
        ts = await self.get_total_stats()
        processed = ts["photos_processed"] + ts["videos_processed"]
        approved = ts["photos_approved"] + ts["videos_approved"]
        return (approved / processed * 100) if processed else 0.0

    async def get_success_rate_24h(self, daily: dict[str, int | str]) -> float:
        """Return success percentage for the last 24 hours."""
        received = int(daily["media_received"])
        errors = (
            int(daily["processing_errors"])
            + int(daily["storage_errors"])
            + int(daily["telegram_errors"])
        )
        return ((received - errors) / received * 100) if received else 100.0

    async def get_busiest_hour(self) -> tuple[Optional[int], int]:
        """Return the hour with the most approved or rejected items."""
        max_count = 0
        max_hour: Optional[int] = None
        for hour in range(24):
            count = int(await self.r.get(_redis_key("hourly", str(hour))) or 0)
            if count > max_count:
                max_count = count
                max_hour = hour
        return max_hour, max_count

    async def get_leaderboard(self, limit: int = 10) -> dict[str, list[dict]]:
        """Return submission/approval/rejection leaderboards."""
        subs_key = _redis_key("leaderboard", "submissions")
        appr_key = _redis_key("leaderboard", "approved")
        rej_key = _redis_key("leaderboard", "rejected")
        subs_raw = dict(await self.r.zrevrange(subs_key, 0, -1, withscores=True))
        appr_raw = dict(await self.r.zrevrange(appr_key, 0, -1, withscores=True))
        rej_raw = dict(await self.r.zrevrange(rej_key, 0, -1, withscores=True))
        all_sources = set(subs_raw) | set(appr_raw) | set(rej_raw)
        entries: list[dict[str, int | float | str]] = []
        for src in all_sources:
            s = int(float(subs_raw.get(src, 0)))
            a = int(float(appr_raw.get(src, 0)))
            r = int(float(rej_raw.get(src, 0)))
            entries.append(
                {
                    "source": src,
                    "submissions": s,
                    "approved": a,
                    "rejected": r,
                    "approved_pct": (a / s * 100) if s else 0,
                    "rejected_pct": (r / s * 100) if s else 0,
                }
            )
        subs_sorted = heapq.nlargest(limit, entries, key=lambda x: x["submissions"])
        appr_sorted = heapq.nlargest(limit, entries, key=lambda x: x["approved"])
        rej_sorted = heapq.nlargest(limit, entries, key=lambda x: x["rejected"])
        return {
            "submissions": subs_sorted,
            "approved": appr_sorted,
            "rejected": rej_sorted,
        }

    async def get_source_acceptance(
        self, limit: int = 8
    ) -> list[dict[str, float | int | str]]:
        """Return per-source acceptance and rejection counts and rates."""

        subs_key = _redis_key("leaderboard", "submissions")
        appr_key = _redis_key("leaderboard", "approved")
        rej_key = _redis_key("leaderboard", "rejected")
        top_sources = await self.r.zrevrange(subs_key, 0, limit - 1, withscores=True)
        if not top_sources:
            return []
        sources = [
            raw_source.decode() if isinstance(raw_source, bytes) else raw_source
            for raw_source, _ in top_sources
        ]
        pipe = self.r.pipeline(transaction=False)
        for source in sources:
            pipe.zscore(appr_key, source)
            pipe.zscore(rej_key, source)
        scores = await pipe.execute()

        approved_scores = scores[::2]
        rejected_scores = scores[1::2]

        entries: list[dict[str, float | int | str]] = []
        for i, (_, raw_submissions) in enumerate(top_sources):
            source = sources[i]
            submissions = int(float(raw_submissions))
            approved = int(float(approved_scores[i] or 0))
            rejected = int(float(rejected_scores[i] or 0))
            decision_total = approved + rejected
            acceptance = (approved / decision_total) * 100 if decision_total else 0.0
            entries.append(
                {
                    "source": source,
                    "submissions": submissions,
                    "approved": approved,
                    "rejected": rejected,
                    "acceptance_rate": acceptance,
                }
            )
        return entries

    async def get_processing_histogram(self) -> dict[str, list[dict[str, float | int]]]:
        """Return histogram buckets for photo and video processing durations."""

        result: dict[str, list[dict[str, float | int]]] = {}
        for media_type in ("photo", "video"):
            key = _redis_key("hist", f"{media_type}_processing")
            raw = await self.r.hgetall(key) or {}
            processed: list[dict[str, float | int]] = []
            for label in self.processing_histogram_labels:
                value = raw.get(label)
                if value is None and isinstance(raw, dict):
                    # aiovalkey may return bytes keys/values
                    value = raw.get(label.encode())
                count = int(value) if value else 0
                processed.append({"label": label, "count": count})
            result[media_type] = processed
        return result

    async def generate_stats_report(self, reset_daily: bool = True) -> str:
        """Return a formatted statistics report for admins."""
        daily = await self.get_daily_stats(reset_if_new_day=reset_daily)
        total = await self.get_total_stats()
        perf = await self.get_performance_metrics()
        approval_24h = await self.get_approval_rate_24h(daily)
        approval_total = await self.get_approval_rate_total()
        success_24h = await self.get_success_rate_24h(daily)
        errors_24h = (
            int(daily.get("processing_errors", 0))
            + int(daily.get("storage_errors", 0))
            + int(daily.get("telegram_errors", 0))
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

        header = "📊 <b>Statistics Report</b> 📊\n"
        daily_section = [
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
        ]
        performance_section = [
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
        ]
        total_section = [
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
        ]
        footer = [f"\n<i>Last reset: {daily.get('last_reset')}</i>"]

        return "\n".join(
            [
                header,
                "\n".join(daily_section),
                "\n".join(performance_section),
                "\n".join(total_section),
                "\n".join(footer),
            ]
        )

    async def reset_daily_stats(self) -> str:
        """Reset daily statistics and hourly counters."""
        for name in self.names:
            await self.r.set(_redis_key("daily", name), 0)
        now = now_utc().isoformat()
        await self.r.set(_redis_meta_key(), now)
        for hour in range(24):
            await self.r.delete(_redis_key("hourly", str(hour)))
        return "Daily statistics have been reset."

    async def reset_leaderboard(self) -> str:
        """Clear all per-source submission and decision statistics."""

        keys = [
            _redis_key("leaderboard", "submissions"),
            _redis_key("leaderboard", "approved"),
            _redis_key("leaderboard", "rejected"),
        ]
        await self.r.delete(*keys)
        return "Leaderboard has been reset."

    async def force_save(self) -> None:
        """Force Valkey to persist data to disk."""
        try:
            await self.r.save()
        except Exception:  # pragma: no cover - best effort
            pass

    async def _record_processing_histogram(
        self, media_type: str, duration: float
    ) -> None:
        """Record ``duration`` in the histogram for ``media_type`` processing."""

        bucket = self._processing_histogram_bucket(duration)
        key = _redis_key("hist", f"{media_type}_processing")
        await self.r.hincrby(key, bucket, 1)

    def _processing_histogram_bucket(self, duration: float) -> str:
        """Return the histogram label bucket for ``duration`` seconds."""

        for idx, bound in enumerate(self.processing_histogram_bounds):
            if duration < bound:
                return self.processing_histogram_labels[idx]
        return self.processing_histogram_labels[-1]


stats = MediaStats()
