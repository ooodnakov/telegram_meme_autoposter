from __future__ import annotations

import datetime

import pytest

from telegram_auto_poster.config import BUCKET_MAIN
from telegram_auto_poster.utils.jobs import (
    _run_clear_event_history,
    _run_refresh_channel_analytics,
    _run_rebuild_dedup_hashes,
    _run_purge_expired_trash,
    _run_reconcile_scheduled_queue,
    _run_reconcile_batch_count,
    _run_reset_daily_stats,
    _run_reset_leaderboard,
    _run_sync_trash_registry,
    _run_refresh_search_text,
)


class _FakeJobContext:
    def __init__(self) -> None:
        self.stats: dict[str, int | float | str] = {}
        self.status_detail: str | None = None
        self.pause_checks = 0

    async def replace_stats(self, stats: dict[str, int | float | str]) -> None:
        self.stats = dict(stats)

    async def increment(self, key: str, amount: int = 1) -> None:
        self.stats[key] = int(self.stats.get(key, 0)) + amount

    async def set_stat(self, key: str, value: int | float | str) -> None:
        self.stats[key] = value

    async def set_status_detail(self, detail: str | None) -> None:
        self.status_detail = detail

    async def wait_if_paused(self) -> None:
        self.pause_checks += 1


@pytest.mark.asyncio
async def test_refresh_search_text_job_rebuilds_cached_metadata(mocker) -> None:
    context = _FakeJobContext()
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.list_files",
        new=mocker.AsyncMock(
            return_value=["photos/processed_1.jpg", "photos/processed_2.jpg"]
        ),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.get_submission_metadata",
        new=mocker.AsyncMock(
            side_effect=[
                {"search_text": "", "ocr_text": "hello"},
                None,
            ]
        ),
    )
    refresh = mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.refresh_submission_search_text",
        new=mocker.AsyncMock(return_value={"search_text": "processed_1.jpg hello"}),
    )

    await _run_refresh_search_text(context)

    refresh.assert_awaited_once_with("processed_1.jpg")
    assert context.stats["objects_total"] == 2
    assert context.stats["objects_indexed"] == 1
    assert context.stats["objects_changed"] == 1
    assert context.stats["objects_without_metadata"] == 1


@pytest.mark.asyncio
async def test_reconcile_scheduled_queue_job_removes_missing_objects(mocker) -> None:
    context = _FakeJobContext()
    mocker.patch(
        "telegram_auto_poster.utils.jobs.get_scheduled_posts",
        return_value=[
            ("scheduled/keep.jpg", 2_000_000_000),
            ("scheduled/missing.jpg", 1),
        ],
    )
    exists = mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.file_exists",
        new=mocker.AsyncMock(side_effect=[True, False]),
    )
    remove = mocker.patch("telegram_auto_poster.utils.jobs.remove_scheduled_post")
    mocker.patch(
        "telegram_auto_poster.utils.jobs.now_utc",
        return_value=datetime.datetime.fromtimestamp(
            1_000_000_000, tz=datetime.timezone.utc
        ),
    )

    await _run_reconcile_scheduled_queue(context)

    assert context.stats["scheduled_total"] == 2
    assert context.stats["items_checked"] == 2
    assert context.stats["kept_valid"] == 1
    assert context.stats["missing_objects"] == 1
    assert context.stats["removed_stale"] == 1
    assert context.stats["overdue_items"] == 1
    assert context.pause_checks == 2
    exists.assert_any_await("scheduled/keep.jpg", BUCKET_MAIN)
    exists.assert_any_await("scheduled/missing.jpg", BUCKET_MAIN)
    remove.assert_called_once_with("scheduled/missing.jpg")


@pytest.mark.asyncio
async def test_purge_expired_trash_job_reports_before_and_after_counts(mocker) -> None:
    context = _FakeJobContext()
    list_files = mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.list_files",
        new=mocker.AsyncMock(
            side_effect=[
                ["trash/photos/a.jpg", "trash/videos/b.mp4"],
                [],
                ["trash/photos/keep.jpg"],
                [],
            ]
        ),
    )
    purge = mocker.patch(
        "telegram_auto_poster.utils.jobs.purge_expired_trash",
        new=mocker.AsyncMock(return_value=["trash/photos/a.jpg"]),
    )

    await _run_purge_expired_trash(context)

    assert context.stats["trash_objects_before"] == 2
    assert context.stats["removed"] == 1
    assert context.stats["trash_objects_after"] == 1
    assert list_files.await_count == 4
    purge.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_trash_registry_job_rebuilds_future_entries(mocker) -> None:
    context = _FakeJobContext()
    future = datetime.datetime(2026, 3, 10, tzinfo=datetime.timezone.utc)
    now = datetime.datetime(2026, 3, 9, tzinfo=datetime.timezone.utc)
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.list_files",
        new=mocker.AsyncMock(
            side_effect=[
                ["trash/photos/a.jpg", "trash/videos/b.mp4"],
                [],
            ]
        ),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.get_submission_metadata",
        new=mocker.AsyncMock(
            side_effect=[
                {"trash_expires_at": future.isoformat()},
                None,
            ]
        ),
    )
    add = mocker.patch(
        "telegram_auto_poster.utils.jobs.add_trashed_post",
        new=mocker.AsyncMock(),
    )
    mocker.patch("telegram_auto_poster.utils.jobs.now_utc", return_value=now)

    await _run_sync_trash_registry(context)

    assert context.stats["trash_objects"] == 2
    assert context.stats["items_checked"] == 2
    assert context.stats["registry_synced"] == 1
    assert context.stats["missing_metadata"] == 1
    add.assert_awaited_once_with("trash/photos/a.jpg", int(future.timestamp()))


@pytest.mark.asyncio
async def test_reconcile_batch_count_job_resets_counter_to_storage_size(
    mocker,
) -> None:
    context = _FakeJobContext()
    redis = mocker.AsyncMock()
    redis.get.return_value = "5"
    mocker.patch("telegram_auto_poster.utils.jobs.get_async_redis_client", return_value=redis)
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.list_files",
        new=mocker.AsyncMock(
            side_effect=[
                ["photos/batch_a.jpg"],
                ["videos/batch_b.mp4", "videos/batch_c.mp4"],
            ]
        ),
    )

    await _run_reconcile_batch_count(context)

    assert context.stats["stored_count"] == 5
    assert context.stats["actual_count"] == 3
    assert context.stats["delta"] == -2
    assert context.stats["updated"] == 1
    redis.set.assert_awaited_once_with("telegram_auto_poster:batch:size", "3")


@pytest.mark.asyncio
async def test_rebuild_dedup_hashes_job_uses_metadata_then_computes_fallback(
    mocker,
) -> None:
    context = _FakeJobContext()
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.list_files",
        new=mocker.AsyncMock(
            return_value=["photos/one.jpg", "videos/two.mp4", "downloads/file.txt"]
        ),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.get_submission_metadata",
        new=mocker.AsyncMock(side_effect=[{"hash": "meta-hash"}, {}]),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.download_from_minio",
        new=mocker.AsyncMock(return_value=("/tmp/two.mp4", "video/mp4")),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.calculate_video_hash",
        return_value="computed-hash",
    )
    add_hash = mocker.patch(
        "telegram_auto_poster.utils.jobs.add_approved_hash",
        side_effect=[True, True],
    )
    update_meta = mocker.patch(
        "telegram_auto_poster.utils.jobs.storage.update_submission_metadata",
        new=mocker.AsyncMock(),
    )
    cleanup = mocker.patch("telegram_auto_poster.utils.jobs.cleanup_temp_file")

    await _run_rebuild_dedup_hashes(context)

    assert context.stats["objects_total"] == 3
    assert context.stats["media_objects"] == 2
    assert context.stats["items_checked"] == 2
    assert context.stats["hashes_from_metadata"] == 1
    assert context.stats["hashes_computed"] == 1
    assert context.stats["hashes_added"] == 2
    add_hash.assert_any_call("meta-hash")
    add_hash.assert_any_call("computed-hash")
    update_meta.assert_awaited_once_with("two.mp4", hash="computed-hash")
    cleanup.assert_called_once_with("/tmp/two.mp4")


@pytest.mark.asyncio
async def test_refresh_channel_analytics_job_waits_for_acknowledgement(mocker) -> None:
    context = _FakeJobContext()
    request = mocker.patch(
        "telegram_auto_poster.utils.jobs.request_channel_analytics_refresh",
        new=mocker.AsyncMock(return_value="req-1"),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.get_completed_channel_analytics_refresh",
        new=mocker.AsyncMock(side_effect=[None, "req-1"]),
    )
    mocker.patch(
        "telegram_auto_poster.utils.jobs.get_cached_channel_analytics",
        new=mocker.AsyncMock(
            return_value={
                "channels": [
                    {"peer": "@a"},
                    {"peer": "@b", "error": "permission denied"},
                ]
            }
        ),
    )
    sleep = mocker.patch("telegram_auto_poster.utils.jobs.asyncio.sleep", new=mocker.AsyncMock())

    await _run_refresh_channel_analytics(context)

    assert context.stats["refresh_requested"] == 1
    assert context.stats["channels_total"] == 2
    assert context.stats["channels_with_errors"] == 1
    assert context.stats["wait_seconds"] == 1
    request.assert_awaited_once()
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_reset_daily_stats_job_persists_reset(mocker) -> None:
    context = _FakeJobContext()
    reset = mocker.patch(
        "telegram_auto_poster.utils.jobs.stats.reset_daily_stats",
        new=mocker.AsyncMock(return_value="Daily statistics have been reset."),
    )
    save = mocker.patch(
        "telegram_auto_poster.utils.jobs.stats.force_save",
        new=mocker.AsyncMock(),
    )

    await _run_reset_daily_stats(context)

    assert context.stats["reset_performed"] == 1
    assert context.status_detail == "Daily statistics have been reset."
    reset.assert_awaited_once()
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_leaderboard_job_persists_reset(mocker) -> None:
    context = _FakeJobContext()
    reset = mocker.patch(
        "telegram_auto_poster.utils.jobs.stats.reset_leaderboard",
        new=mocker.AsyncMock(return_value="Leaderboard has been reset."),
    )
    save = mocker.patch(
        "telegram_auto_poster.utils.jobs.stats.force_save",
        new=mocker.AsyncMock(),
    )

    await _run_reset_leaderboard(context)

    assert context.stats["reset_performed"] == 1
    assert context.status_detail == "Leaderboard has been reset."
    reset.assert_awaited_once()
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_event_history_job_clears_history(mocker) -> None:
    context = _FakeJobContext()
    clear = mocker.patch(
        "telegram_auto_poster.utils.jobs.clear_event_history",
        new=mocker.AsyncMock(),
    )

    await _run_clear_event_history(context)

    assert context.stats["reset_performed"] == 1
    assert context.status_detail == "Event history cleared"
    clear.assert_awaited_once()
