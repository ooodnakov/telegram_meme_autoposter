from types import SimpleNamespace

import pytest
import sqlalchemy
from pytest_mock import MockerFixture
from telegram_auto_poster.config import SCHEDULED_PATH


@pytest.fixture
def commands(mocker: MockerFixture):
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    mocker.patch("sqlalchemy.create_engine", lambda *a, **k: engine)
    from telegram_auto_poster.bot import commands as commands_module

    return commands_module


@pytest.fixture
def mock_bot_and_context(mocker: MockerFixture, commands):
    update = SimpleNamespace(
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
        effective_message=SimpleNamespace(message_id=1),
    )
    bot = SimpleNamespace(
        send_media_group=mocker.AsyncMock(),
        send_message=mocker.AsyncMock(),
    )
    context = SimpleNamespace(
        bot=bot,
        bot_data={
            "target_channel_id": 123,
            "photo_batch": ["file1"],
            "video_batch": ["file2"],
        },
    )
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    return update, context


@pytest.mark.asyncio
async def test_send_batch_photo_closes_file_and_cleans(
    tmp_path, mocker: MockerFixture, mock_bot_and_context, commands
):
    temp_file = tmp_path / "photo.jpg"
    mocker.patch.object(
        commands,
        "list_batch_files",
        new=mocker.AsyncMock(return_value=["photo.jpg"]),
    )
    mocker.patch(
        "telegram_auto_poster.bot.commands.download_from_minio",
        return_value=(str(temp_file), "ext"),
    )
    mock_file = mocker.mock_open(read_data=b"data")
    mocker.patch("builtins.open", mock_file)
    mock_storage = mocker.patch("telegram_auto_poster.bot.commands.storage")
    mock_storage.get_submission_metadata = mocker.AsyncMock(return_value=None)
    mock_storage.delete_file = mocker.AsyncMock()
    mock_storage.mark_notified = mocker.AsyncMock()
    mock_stats = mocker.patch("telegram_auto_poster.utils.stats.stats")
    mock_stats.record_approved = mocker.AsyncMock()
    mock_stats.record_batch_sent = mocker.AsyncMock()
    mock_cleanup = mocker.patch("telegram_auto_poster.bot.commands.cleanup_temp_file")
    _ = mocker.patch(
        "telegram_auto_poster.bot.commands.notify_user",
        new=mocker.AsyncMock(),
    )
    mocker.patch.object(commands.db, "decrement_batch_count", new=mocker.AsyncMock())

    update, context = mock_bot_and_context

    await commands.send_batch_command(update, context)

    context.bot.send_media_group.assert_awaited_once()
    sent_args = context.bot.send_media_group.call_args.kwargs
    assert sent_args["chat_id"] == 123
    media = sent_args["media"]
    assert len(media) == 1
    mock_file().close.assert_called_once()
    mock_cleanup.assert_called_once_with(str(temp_file))


@pytest.mark.asyncio
async def test_start_command(mocker: MockerFixture, commands):
    """Test the start command."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    await commands.start_command(update, context)
    update.message.reply_text.assert_awaited_once_with(
        "Привет! Присылай сюда свои мемы)"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id, has_admin",
    [
        (456, False),
        (123, True),
    ],
)
async def test_help_command(mocker: MockerFixture, commands, user_id, has_admin):
    """Test the help command for different user roles."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = SimpleNamespace(bot_data={"admin_ids": [123]})
    await commands.help_command(update, context)
    update.message.reply_text.assert_awaited_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Команды пользователя:" in call_args
    assert ("Команды администратора:" in call_args) == has_admin


@pytest.mark.asyncio
async def test_get_chat_id_command(mocker: MockerFixture, commands):
    """Test the get_chat_id command."""
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=789),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    await commands.get_chat_id_command(update, context)
    update.message.reply_text.assert_awaited_once_with("This chat ID is: 789")


@pytest.mark.asyncio
async def test_send_batch_video_closes_file_and_cleans(
    tmp_path, mocker: MockerFixture, mock_bot_and_context, commands
):
    temp_file = tmp_path / "video.mp4"
    mocker.patch.object(
        commands,
        "list_batch_files",
        new=mocker.AsyncMock(return_value=["video.mp4"]),
    )
    mocker.patch(
        "telegram_auto_poster.bot.commands.download_from_minio",
        return_value=(str(temp_file), "ext"),
    )
    mock_file = mocker.mock_open(read_data=b"data")
    mocker.patch("builtins.open", mock_file)
    mock_storage = mocker.patch("telegram_auto_poster.bot.commands.storage")
    mock_storage.get_submission_metadata = mocker.AsyncMock(return_value=None)
    mock_storage.delete_file = mocker.AsyncMock()
    mock_storage.mark_notified = mocker.AsyncMock()
    mock_stats = mocker.patch("telegram_auto_poster.utils.stats.stats")
    mock_stats.record_approved = mocker.AsyncMock()
    mock_stats.record_batch_sent = mocker.AsyncMock()
    mock_cleanup = mocker.patch("telegram_auto_poster.bot.commands.cleanup_temp_file")
    _ = mocker.patch(
        "telegram_auto_poster.bot.commands.notify_user",
        new=mocker.AsyncMock(),
    )
    mocker.patch.object(commands.db, "decrement_batch_count", new=mocker.AsyncMock())

    update, context = mock_bot_and_context

    await commands.send_batch_command(update, context)

    context.bot.send_media_group.assert_awaited_once()
    sent_args = context.bot.send_media_group.call_args.kwargs
    assert sent_args["chat_id"] == 123
    media = sent_args["media"]
    assert len(media) == 1
    mock_file().close.assert_called_once()
    mock_cleanup.assert_called_once_with(str(temp_file))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report, expected",
    [
        ("report", "report"),
        ("", "No statistics available."),
    ],
)
async def test_stats_command(mocker: MockerFixture, commands, report, expected):
    """Test the stats command with different report outputs."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mock_stats = mocker.patch.object(commands, "stats")
    mock_stats.generate_stats_report = mocker.AsyncMock(return_value=report)

    await commands.stats_command(update, context)

    mock_stats.generate_stats_report.assert_awaited_once()
    update.message.reply_text.assert_awaited_once_with(expected, parse_mode="HTML")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response, expected",
    [
        ("reset", "reset"),
        ("", "Daily statistics have been reset."),
    ],
)
async def test_reset_stats_command(mocker: MockerFixture, commands, response, expected):
    """Test the reset_stats command responses."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mock_stats = mocker.patch.object(commands, "stats")
    mock_stats.reset_daily_stats = mocker.AsyncMock(return_value=response)

    await commands.reset_stats_command(update, context)

    mock_stats.reset_daily_stats.assert_awaited_once()
    update.message.reply_text.assert_awaited_once_with(expected)


@pytest.mark.asyncio
async def test_save_stats_command(mocker: MockerFixture, commands):
    """Test the save_stats command."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mock_stats = mocker.patch.object(commands, "stats")
    mock_stats.force_save = mocker.AsyncMock()

    await commands.save_stats_command(update, context)

    mock_stats.force_save.assert_awaited_once()
    update.message.reply_text.assert_awaited_once_with("Stats saved!")


@pytest.mark.asyncio
async def test_stats_command_handles_exception(mocker: MockerFixture, commands):
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mock_stats = mocker.patch.object(commands, "stats")
    mock_stats.generate_stats_report = mocker.AsyncMock(side_effect=Exception("boom"))

    await commands.stats_command(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "Sorry, there was an error generating the statistics report."
    )


@pytest.mark.asyncio
async def test_reset_stats_command_handles_exception(mocker: MockerFixture, commands):
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mock_stats = mocker.patch.object(commands, "stats")
    mock_stats.reset_daily_stats = mocker.AsyncMock(side_effect=Exception("boom"))

    await commands.reset_stats_command(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "Sorry, there was an error resetting the statistics."
    )


@pytest.mark.asyncio
async def test_save_stats_command_handles_exception(mocker: MockerFixture, commands):
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = mocker.MagicMock()
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mock_stats = mocker.patch.object(commands, "stats")
    mock_stats.force_save = mocker.AsyncMock(side_effect=Exception("boom"))

    await commands.save_stats_command(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "Sorry, there was an error saving the statistics."
    )


@pytest.mark.asyncio
async def test_post_scheduled_media_job_uses_correct_path(
    mocker: MockerFixture, commands
):
    """Ensure scheduled media job uses full stored paths without re-prefixing."""
    scheduled_path = f"{SCHEDULED_PATH}/foo.jpg"
    mocker.patch.object(
        commands.db, "get_scheduled_posts", return_value=[(scheduled_path, 0)]
    )
    mocker.patch.object(
        commands,
        "download_from_minio",
        new=mocker.AsyncMock(return_value=("/tmp/foo.jpg", None)),
    )
    mocker.patch.object(commands, "send_media_to_telegram", new=mocker.AsyncMock())
    mocker.patch.object(commands.storage, "delete_file", new=mocker.AsyncMock())
    mocker.patch.object(commands.db, "remove_scheduled_post")

    context = SimpleNamespace(bot=SimpleNamespace(), bot_data={"target_channel_id": 1})

    await commands.post_scheduled_media_job(context)

    commands.download_from_minio.assert_awaited_once_with(
        scheduled_path, commands.BUCKET_MAIN
    )
    commands.storage.delete_file.assert_awaited_once_with(
        scheduled_path, commands.BUCKET_MAIN
    )
    commands.db.remove_scheduled_post.assert_called_once_with(scheduled_path)


@pytest.mark.asyncio
async def test_sch_command_uses_preview(mocker: MockerFixture, commands):
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=99),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = SimpleNamespace(bot=SimpleNamespace())
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mocker.patch.object(
        commands.db, "get_scheduled_posts", return_value=[("p1.jpg", 0)]
    )
    preview = mocker.patch.object(
        commands, "send_schedule_preview", new=mocker.AsyncMock()
    )

    await commands.sch_command(update, context)

    preview.assert_awaited_once_with(context.bot, 99, "p1.jpg", 0)


@pytest.mark.asyncio
async def test_batch_command_uses_preview(mocker: MockerFixture, commands):
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=99),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    context = SimpleNamespace(bot=SimpleNamespace())
    mocker.patch.object(commands, "check_admin_rights", return_value=True)
    mocker.patch.object(
        commands, "list_batch_files", new=mocker.AsyncMock(return_value=["p1.jpg"])
    )
    preview = mocker.patch.object(
        commands, "send_batch_preview", new=mocker.AsyncMock()
    )

    await commands.batch_command(update, context)

    preview.assert_awaited_once_with(context.bot, 99, "p1.jpg", 0)


@pytest.mark.asyncio
async def test_send_schedule_preview_builds_markup(tmp_path, mocker: MockerFixture):
    from telegram_auto_poster.bot.callbacks import send_schedule_preview

    temp_file = tmp_path / "t.jpg"
    temp_file.write_bytes(b"data")

    mocker.patch(
        "telegram_auto_poster.bot.callbacks.download_from_minio",
        return_value=(str(temp_file), None),
    )
    edit_mock = mocker.AsyncMock()
    msg = SimpleNamespace(edit_reply_markup=edit_mock)
    send_media = mocker.AsyncMock(return_value=msg)
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_media_to_telegram", send_media
    )

    bot = SimpleNamespace()
    await send_schedule_preview(bot, 1, "photos/a.jpg", 2)

    send_media.assert_awaited_once()
    assert edit_mock.awaited
    markup = edit_mock.call_args.kwargs["reply_markup"]
    texts = [b.text for b in markup.inline_keyboard[0]]
    assert texts == ["Prev", "Unschedule", "Push", "Next"]
    row = markup.inline_keyboard[0]
    assert row[1].callback_data == "/sch_unschedule:2"
    assert row[2].callback_data == "/sch_push:2"
    assert row[3].callback_data == "/sch_next:2"
