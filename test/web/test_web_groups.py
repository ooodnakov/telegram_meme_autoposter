import pytest
from pytest_mock import MockerFixture
from telegram_auto_poster.config import PHOTOS_PATH
from telegram_auto_poster.web.app import _gather_posts


@pytest.mark.asyncio
async def test_gather_posts_groups_by_group_id(mocker: MockerFixture):
    objects = [
        f"{PHOTOS_PATH}/processed_a.jpg",
        f"{PHOTOS_PATH}/processed_b.jpg",
        f"{PHOTOS_PATH}/processed_c.jpg",
    ]
    mocker.patch(
        "telegram_auto_poster.web.app.storage.list_files",
        side_effect=[objects, []],
    )

    async def fake_get_meta(name):
        if name in {"processed_a.jpg", "processed_b.jpg"}:
            return {"group_id": "g1"}
        return {}

    async def fake_get_url(obj):
        return f"http://example.com/{obj}"

    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_submission_metadata",
        side_effect=fake_get_meta,
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        side_effect=fake_get_url,
    )

    posts = await _gather_posts(False)
    assert len(posts) == 2
    lengths = sorted(len(p["items"]) for p in posts)
    assert lengths == [1, 2]
