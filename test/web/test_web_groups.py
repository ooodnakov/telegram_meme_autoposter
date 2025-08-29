import pytest
from pytest_mock import MockerFixture
from starlette.requests import Request
from starlette.responses import Response
from telegram_auto_poster.config import PHOTOS_PATH
from telegram_auto_poster.web.app import _gather_posts, _render_posts_page


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


@pytest.mark.asyncio
async def test_gather_posts_filters_suggestions(mocker: MockerFixture):
    async def fake_list_files(bucket, prefix):
        if prefix.startswith(f"{PHOTOS_PATH}/processed_"):
            return [
                f"{PHOTOS_PATH}/processed_sug.jpg",
                f"{PHOTOS_PATH}/processed_post.jpg",
            ]
        return []

    mocker.patch(
        "telegram_auto_poster.web.app.storage.list_files",
        side_effect=fake_list_files,
    )

    async def fake_get_meta(name):
        if name == "processed_sug.jpg":
            return {"user_id": "u1"}
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

    suggestions = await _gather_posts(True)
    assert len(suggestions) == 1
    assert suggestions[0]["items"][0]["path"].endswith("processed_sug.jpg")

    posts = await _gather_posts(False)
    assert len(posts) == 1
    assert posts[0]["items"][0]["path"].endswith("processed_post.jpg")


@pytest.mark.asyncio
async def test_render_posts_page_uses_partial_template(mocker: MockerFixture):
    posts = [
        {
            "items": [
                {
                    "path": f"{PHOTOS_PATH}/processed_post.jpg",
                    "url": "http://example.com/a.jpg",
                    "is_image": True,
                    "is_video": False,
                }
            ]
        }
    ]
    gather = mocker.patch(
        "telegram_auto_poster.web.app._gather_posts",
        new=mocker.AsyncMock(return_value=posts),
    )
    template = mocker.patch(
        "telegram_auto_poster.web.app.templates.TemplateResponse",
        return_value=Response(),
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"hx-request", b"true")],
            "query_string": b"",
        }
    )
    await _render_posts_page(
        request,
        only_suggestions=True,
        origin="suggestions",
        alt_text="suggestion",
        empty_message="none",
        template_name="suggestions.html",
    )
    gather.assert_awaited_once_with(True)
    template.assert_called_once()
    assert template.call_args[0][0] == "_post_grid.html"
    ctx = template.call_args[0][1]
    assert ctx["posts"] == posts
    assert ctx["origin"] == "suggestions"
