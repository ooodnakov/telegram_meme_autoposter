import pytest
from pytest_mock import MockerFixture

from telegram_auto_poster.config import PHOTOS_PATH, TRASH_PATH
from telegram_auto_poster.web.app import _gather_posts, _gather_trash


@pytest.mark.asyncio
async def test_gather_posts_groups_by_group_id(mocker: MockerFixture):
    objects = [
        f"{PHOTOS_PATH}/processed_a.jpg",
        f"{PHOTOS_PATH}/processed_b.jpg",
        f"{PHOTOS_PATH}/processed_c.jpg",
    ]

    mocker.patch(
        "telegram_auto_poster.web.app._list_media",
        new=mocker.AsyncMock(return_value=objects),
    )

    async def fake_get_meta(name):
        if name in {"processed_a.jpg", "processed_b.jpg"}:
            return {
                "group_id": "g1",
                "caption": "group caption",
                "source": "@channel",
                "user_id": 42,
            }
        return {"caption": "single caption", "source": "@single"}

    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_submission_metadata",
        new=mocker.AsyncMock(side_effect=fake_get_meta),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        new=mocker.AsyncMock(side_effect=lambda obj: f"http://example.com/{obj}"),
    )

    posts = await _gather_posts(True)
    assert len(posts) == 1
    assert posts[0]["count"] == 2
    assert posts[0]["caption"] == "group caption"
    assert posts[0]["source"] == "@channel"
    assert posts[0]["submitter"]["user_id"] == 42

    posts = await _gather_posts(False)
    assert len(posts) == 1
    assert posts[0]["caption"] == "single caption"


@pytest.mark.asyncio
async def test_gather_trash_includes_retention_metadata(mocker: MockerFixture):
    objects = [f"{TRASH_PATH}/{PHOTOS_PATH}/trashed.jpg"]
    mocker.patch(
        "telegram_auto_poster.web.app.purge_expired_trash",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._list_trash_media",
        new=mocker.AsyncMock(return_value=objects),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_submission_metadata",
        new=mocker.AsyncMock(
            return_value={
                "trashed_at": "2026-03-08T10:00:00+00:00",
                "trash_expires_at": "2026-03-09T10:00:00+00:00",
            }
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        new=mocker.AsyncMock(return_value="http://example.com/trashed.jpg"),
    )

    posts = await _gather_trash()
    assert len(posts) == 1
    assert posts[0]["items"][0]["url"] == "http://example.com/trashed.jpg"
    assert posts[0]["trashed_at"] == "2026-03-08T10:00:00+00:00"
    assert posts[0]["expires_at"] == "2026-03-09T10:00:00+00:00"
