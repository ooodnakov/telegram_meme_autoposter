from __future__ import annotations

import pytest

from telegram_auto_poster.utils.jobs import _run_refresh_search_text


class _FakeJobContext:
    def __init__(self) -> None:
        self.stats: dict[str, int | float | str] = {}
        self.status_detail: str | None = None

    async def replace_stats(self, stats: dict[str, int | float | str]) -> None:
        self.stats = dict(stats)

    async def increment(self, key: str, amount: int = 1) -> None:
        self.stats[key] = int(self.stats.get(key, 0)) + amount

    async def set_status_detail(self, detail: str | None) -> None:
        self.status_detail = detail


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
