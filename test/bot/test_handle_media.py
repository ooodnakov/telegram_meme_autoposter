import asyncio
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture
from telegram_auto_poster.bot import handlers


@pytest.fixture
def mock_update(mocker: MockerFixture):
    """Fixture to create a mock update object."""
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        message=SimpleNamespace(
            photo=None,
            video=None,
            reply_text=mocker.AsyncMock(),
        ),
    )
    return update


def run(coro):
    return asyncio.run(coro)


@pytest.mark.asyncio
async def test_handle_media_photo(mocker: MockerFixture, mock_update, mock_config):
    mock_update.message.photo = [object()]
    context = mocker.MagicMock()
    handle_photo_mock = mocker.patch.object(
        handlers, "handle_photo", new_callable=mocker.AsyncMock
    )

    await handlers.handle_media(mock_update, context)

    handle_photo_mock.assert_awaited_once_with(mock_update, context, 123)
    mock_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_media_video(mocker: MockerFixture, mock_update, mock_config):
    mock_update.message.video = object()
    context = mocker.MagicMock()
    handle_video_mock = mocker.patch.object(
        handlers, "handle_video", new_callable=mocker.AsyncMock
    )

    await handlers.handle_media(mock_update, context)

    handle_video_mock.assert_awaited_once_with(mock_update, context, 123)
    mock_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_media_exception(mocker: MockerFixture, mock_update, mock_config):
    mock_update.message.photo = [object()]
    context = mocker.MagicMock()
    mocker.patch.object(
        handlers,
        "handle_photo",
        new_callable=mocker.AsyncMock,
        side_effect=Exception("boom"),
    )

    await handlers.handle_media(mock_update, context)

    mock_update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_photo_wrapper(mocker: MockerFixture, mock_config):
    handle_media_type_mock = mocker.patch.object(
        handlers, "handle_media_type", new_callable=mocker.AsyncMock
    )

    await handlers.handle_photo("update", "context", 1)

    handle_media_type_mock.assert_awaited_once_with(
        "update", "context", 1, "photo", ".jpg", handlers.calculate_image_hash
    )


@pytest.mark.asyncio
async def test_handle_video_wrapper(mocker: MockerFixture, mock_config):
    handle_media_type_mock = mocker.patch.object(
        handlers, "handle_media_type", new_callable=mocker.AsyncMock
    )

    await handlers.handle_video("update", "context", 1)

    handle_media_type_mock.assert_awaited_once_with(
        "update", "context", 1, "video", ".mp4", handlers.calculate_video_hash
    )
