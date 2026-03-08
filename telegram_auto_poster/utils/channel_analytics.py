"""Telegram channel analytics caching backed by the running Telethon client."""

from __future__ import annotations

import datetime
import json
from datetime import timedelta
from typing import Any, Sequence

from loguru import logger
from telethon import TelegramClient, functions, types

from telegram_auto_poster.utils.db import _redis_key, get_async_redis_client
from telegram_auto_poster.utils.timezone import now_utc

CHANNEL_ANALYTICS_CACHE_TTL_SECONDS = 24 * 60 * 60
CHANNEL_ANALYTICS_REFRESH_THRESHOLD_SECONDS = 60 * 60


def _cache_key() -> str:
    """Return the Valkey key used for cached Telegram analytics."""

    return _redis_key("cache", "telegram_channel_analytics")


def _serialize_abs_metric(
    key: str, value: types.StatsAbsValueAndPrev
) -> dict[str, str | float]:
    """Normalize an absolute Telegram stats metric."""

    current = float(value.current)
    previous = float(value.previous)
    delta = current - previous
    delta_pct = (delta / previous * 100) if previous else (100.0 if current else 0.0)
    return {
        "key": key,
        "current": current,
        "previous": previous,
        "delta": delta,
        "delta_pct": delta_pct,
    }


def _serialize_percent_metric(
    key: str, value: types.StatsPercentValue
) -> dict[str, str | float]:
    """Normalize a percent Telegram stats metric."""

    part = float(value.part)
    total = float(value.total)
    percentage = (part / total * 100) if total else 0.0
    return {
        "key": key,
        "part": part,
        "total": total,
        "percentage": percentage,
    }


def _format_graph_x(value: Any) -> tuple[str, str]:
    """Return an ISO value and short label for the graph x-axis."""

    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            ts = float(value) / 1000
        else:
            ts = float(value)
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
        return dt.isoformat(), dt.strftime("%b %d")
    return str(value), str(value)


async def _resolve_graph(
    client: TelegramClient, graph: types.TypeStatsGraph
) -> types.TypeStatsGraph:
    """Resolve async graph handles into concrete graph payloads."""

    if isinstance(graph, types.StatsGraphAsync):
        return await client(functions.stats.LoadAsyncGraphRequest(token=graph.token))
    return graph


async def _serialize_graph(
    client: TelegramClient,
    graph: types.TypeStatsGraph,
    *,
    key: str,
    title_key: str,
) -> dict[str, object] | None:
    """Convert a Telegram graph into a frontend-friendly structure."""

    resolved = await _resolve_graph(client, graph)
    if isinstance(resolved, types.StatsGraphError):
        return {
            "key": key,
            "title_key": title_key,
            "error": resolved.error,
        }
    if not isinstance(resolved, types.StatsGraph):
        return None

    try:
        payload = json.loads(resolved.json.data)
    except json.JSONDecodeError:
        return None

    columns = payload.get("columns")
    types_map = payload.get("types") or {}
    names = payload.get("names") or {}
    colors = payload.get("colors") or {}
    if not isinstance(columns, list) or not isinstance(types_map, dict):
        return None

    keyed_columns: dict[str, list[Any]] = {}
    for column in columns:
        if not isinstance(column, list) or not column:
            continue
        keyed_columns[str(column[0])] = list(column[1:])

    x_key = next((name for name, kind in types_map.items() if kind == "x"), None)
    if not x_key or x_key not in keyed_columns:
        return None

    x_values = keyed_columns.pop(x_key)
    points: list[dict[str, Any]] = []
    for index, x_value in enumerate(x_values):
        x_iso, x_label = _format_graph_x(x_value)
        point: dict[str, Any] = {
            "x": x_iso,
            "label": x_label,
            "raw_x": x_value,
        }
        for series_key, values in keyed_columns.items():
            point[series_key] = values[index] if index < len(values) else None
        points.append(point)

    series = [
        {
            "key": series_key,
            "label": names.get(series_key, series_key),
            "color": colors.get(series_key),
            "type": types_map.get(series_key, "line"),
        }
        for series_key in keyed_columns
    ]
    if not series or not points:
        return None

    return {
        "key": key,
        "title_key": title_key,
        "points": points,
        "series": series,
        "stacked": bool(payload.get("stacked")),
        "percentage": bool(payload.get("percentage")),
    }


def _message_link(username: str | None, msg_id: int) -> str | None:
    """Return a shareable Telegram link for ``msg_id`` when possible."""

    if not username:
        return None
    return f"https://t.me/{username}/{msg_id}"


async def _serialize_broadcast_stats(
    client: TelegramClient,
    raw_channel: str,
    entity: types.TypeChannel,
    stats: types.stats.BroadcastStats,
) -> dict[str, object]:
    """Serialize broadcast channel stats."""

    graphs: list[dict[str, object]] = []
    for key, title_key, graph in (
        ("followers", "followersGraph", stats.followers_graph),
        ("interactions", "interactionsGraph", stats.interactions_graph),
        ("top_hours", "topHoursGraph", stats.top_hours_graph),
        ("views_by_source", "viewsBySourceGraph", stats.views_by_source_graph),
    ):
        parsed = await _serialize_graph(client, graph, key=key, title_key=title_key)
        if parsed:
            graphs.append(parsed)

    username = getattr(entity, "username", None)
    recent_posts = []
    for post in stats.recent_posts_interactions[:5]:
        if isinstance(post, types.PostInteractionCountersMessage):
            recent_posts.append(
                {
                    "message_id": post.msg_id,
                    "views": post.views,
                    "forwards": post.forwards,
                    "reactions": post.reactions,
                    "link": _message_link(username, post.msg_id),
                }
            )

    return {
        "peer": raw_channel,
        "id": getattr(entity, "id", None),
        "title": getattr(entity, "title", None) or username or raw_channel,
        "username": username,
        "kind": "broadcast",
        "period": {
            "start": stats.period.min_date.isoformat() if stats.period.min_date else None,
            "end": stats.period.max_date.isoformat() if stats.period.max_date else None,
        },
        "summary_metrics": [
            _serialize_abs_metric("followers", stats.followers),
            _serialize_abs_metric("viewsPerPost", stats.views_per_post),
            _serialize_abs_metric("sharesPerPost", stats.shares_per_post),
            _serialize_abs_metric("reactionsPerPost", stats.reactions_per_post),
        ],
        "ratio_metrics": [
            _serialize_percent_metric("enabledNotifications", stats.enabled_notifications)
        ],
        "graphs": graphs,
        "recent_posts": recent_posts,
    }


async def _serialize_megagroup_stats(
    client: TelegramClient,
    raw_channel: str,
    entity: types.TypeChannel,
    stats: types.stats.MegagroupStats,
) -> dict[str, object]:
    """Serialize megagroup stats."""

    graphs: list[dict[str, object]] = []
    for key, title_key, graph in (
        ("members", "membersGraph", stats.members_graph),
        ("messages", "messagesGraph", stats.messages_graph),
        ("top_hours", "topHoursGraph", stats.top_hours_graph),
        ("weekdays", "weekdaysGraph", stats.weekdays_graph),
    ):
        parsed = await _serialize_graph(client, graph, key=key, title_key=title_key)
        if parsed:
            graphs.append(parsed)

    return {
        "peer": raw_channel,
        "id": getattr(entity, "id", None),
        "title": getattr(entity, "title", None) or getattr(entity, "username", None) or raw_channel,
        "username": getattr(entity, "username", None),
        "kind": "megagroup",
        "period": {
            "start": stats.period.min_date.isoformat() if stats.period.min_date else None,
            "end": stats.period.max_date.isoformat() if stats.period.max_date else None,
        },
        "summary_metrics": [
            _serialize_abs_metric("members", stats.members),
            _serialize_abs_metric("messages", stats.messages),
            _serialize_abs_metric("viewers", stats.viewers),
            _serialize_abs_metric("posters", stats.posters),
        ],
        "ratio_metrics": [],
        "graphs": graphs,
        "recent_posts": [],
    }


async def _fetch_channel_payload(
    client: TelegramClient,
    channel: str,
) -> dict[str, object]:
    """Fetch and serialize Telegram stats for one channel."""

    entity = await client.get_entity(channel)
    stats = await client.get_stats(entity)
    if isinstance(stats, types.stats.BroadcastStats):
        return await _serialize_broadcast_stats(client, channel, entity, stats)
    if isinstance(stats, types.stats.MegagroupStats):
        return await _serialize_megagroup_stats(client, channel, entity, stats)
    return {
        "peer": channel,
        "id": getattr(entity, "id", None),
        "title": getattr(entity, "title", None) or getattr(entity, "username", None) or channel,
        "username": getattr(entity, "username", None),
        "kind": "unknown",
        "error": f"Unsupported stats payload: {type(stats).__name__}",
        "summary_metrics": [],
        "ratio_metrics": [],
        "graphs": [],
        "recent_posts": [],
    }


async def get_cached_channel_analytics() -> dict[str, object] | None:
    """Return cached Telegram channel analytics from Valkey."""

    client = get_async_redis_client()
    raw = await client.get(_cache_key())
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def refresh_channel_analytics_cache(
    client: TelegramClient,
    channels: Sequence[str],
    *,
    force: bool = False,
) -> dict[str, object] | None:
    """Refresh the cached Telegram channel analytics when stale."""

    cache = get_async_redis_client()
    key = _cache_key()
    cached = await get_cached_channel_analytics()
    ttl = await cache.ttl(key)
    if (
        not force
        and cached
        and isinstance(ttl, int)
        and ttl > CHANNEL_ANALYTICS_REFRESH_THRESHOLD_SECONDS
    ):
        return cached

    if not channels:
        return cached

    fetched_at = now_utc()
    channel_payloads: list[dict[str, object]] = []
    for channel in channels:
        try:
            channel_payloads.append(await _fetch_channel_payload(client, channel))
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning(f"Failed to fetch Telegram analytics for {channel}: {exc}")
            channel_payloads.append(
                {
                    "peer": channel,
                    "title": channel,
                    "kind": "unknown",
                    "error": str(exc),
                    "summary_metrics": [],
                    "ratio_metrics": [],
                    "graphs": [],
                    "recent_posts": [],
                }
            )

    payload = {
        "fetched_at": fetched_at.isoformat(),
        "expires_at": (fetched_at + timedelta(seconds=CHANNEL_ANALYTICS_CACHE_TTL_SECONDS)).isoformat(),
        "channels": channel_payloads,
    }
    await cache.setex(
        key,
        CHANNEL_ANALYTICS_CACHE_TTL_SECONDS,
        json.dumps(payload, default=str),
    )
    return payload
