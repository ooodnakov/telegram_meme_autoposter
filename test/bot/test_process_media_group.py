from types import SimpleNamespace

import pytest
from telegram import InputMediaPhoto, InputMediaVideo
from telegram_auto_poster.bot.handlers import process_media_group


@pytest.mark.asyncio
async def test_process_media_group(mocker, tmp_path):
    application = SimpleNamespace(bot=mocker.AsyncMock())
    send_media_group_mock = application.bot.send_media_group
    send_media_group_mock.return_value = [
        SimpleNamespace(chat_id=1, message_id=1),
        SimpleNamespace(chat_id=1, message_id=2),
    ]

    mocker.patch(
        "telegram_auto_poster.bot.handlers.add_watermark_to_image",
        new_callable=mocker.AsyncMock,
    )
    mocker.patch(
        "telegram_auto_poster.bot.handlers.add_watermark_to_video",
        new_callable=mocker.AsyncMock,
    )
    mocker.patch(
        "telegram_auto_poster.bot.handlers.stats.record_processed",
        new_callable=mocker.AsyncMock,
    )
    storage_mock = mocker.patch(
        "telegram_auto_poster.bot.handlers.storage.store_review_message",
        new_callable=mocker.AsyncMock,
    )

    photo_processed = tmp_path / "processed_photo.jpg"
    photo_processed.touch()
    video_processed = tmp_path / "processed_video.mp4"
    video_processed.touch()

    mocker.patch(
        "telegram_auto_poster.bot.handlers.download_from_minio",
        new_callable=mocker.AsyncMock,
        side_effect=[(str(photo_processed), None), (str(video_processed), None)],
    )

    files = [
        ("photo1.jpg", "photo1.jpg", "photo"),
        ("video1.mp4", "video1.mp4", "video"),
    ]

    await process_media_group("caption", files, "chat", application)

    send_media_group_mock.assert_awaited_once()
    args, kwargs = send_media_group_mock.await_args
    media = args[1] if len(args) > 1 else kwargs["media"]
    assert len(media) == 2
    assert isinstance(media[0], InputMediaPhoto)
    assert isinstance(media[1], InputMediaVideo)
    assert storage_mock.await_count == 2
