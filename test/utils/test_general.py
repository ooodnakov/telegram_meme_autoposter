import io
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram_auto_poster.utils.general import (
    MinioError,
    cleanup_temp_file,
    download_from_minio,
    extract_file_paths,
    extract_filename,
    extract_paths_from_message,
    get_file_extension,
    send_group_media,
)
from telegram_auto_poster.utils.stats import stats
from telegram_auto_poster.utils.storage import storage


@pytest.mark.parametrize(
    "text, expected",
    [
        ("intro text\nphotos/processed_img.jpg", "photos/processed_img.jpg"),
        ("line1\nline2", "line2"),
        ("", None),
        ("   ", None),
        ("single_line", "single_line"),
        ("  line1\n  line2  ", "line2"),
    ],
)
def test_extract_filename(text, expected):
    assert extract_filename(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("photos/a.jpg\nnot-a-path\nvideos/b.mp4", ["photos/a.jpg", "videos/b.mp4"]),
        ("just text", []),
        ("", []),
        ("photos/a.jpg\nphotos/b.jpg", ["photos/a.jpg", "photos/b.jpg"]),
        ("videos/a.mp4", ["videos/a.mp4"]),
        (
            "trash/photos/a.jpg\ntrash/videos/b.mp4",
            ["trash/photos/a.jpg", "trash/videos/b.mp4"],
        ),
        ("   ", []),
    ],
)
def test_extract_file_paths(text, expected):
    assert extract_file_paths(text) == expected


@pytest.mark.parametrize(
    "message, expected",
    [
        (
            SimpleNamespace(caption="photos/a.jpg\nvideos/b.mp4", text=None),
            ["photos/a.jpg", "videos/b.mp4"],
        ),
        (
            SimpleNamespace(text="intro\nline2", caption=None),
            ["line2"],
        ),
        (
            SimpleNamespace(text="trash/photos/a.jpg", caption=None),
            ["trash/photos/a.jpg"],
        ),
        (
            SimpleNamespace(text="", caption=None),
            [],
        ),
        (
            SimpleNamespace(text=None, caption=None),
            [],
        ),
        (
            None,
            [],
        ),
        (
            SimpleNamespace(),
            [],
        ),
    ],
)
def test_extract_paths_from_message(message, expected):
    assert extract_paths_from_message(message) == expected


def test_cleanup_temp_file_removes_file(tmp_path):
    temp_file = tmp_path / "temp.txt"
    temp_file.write_text("data")
    cleanup_temp_file(str(temp_file))
    assert not temp_file.exists()


def test_cleanup_temp_file_none_path():
    # Should not raise when file_path is None
    cleanup_temp_file(None)


def test_cleanup_temp_file_non_existent_file(tmp_path):
    # Should not raise when file does not exist
    non_existent_file = tmp_path / "non_existent_file.txt"
    cleanup_temp_file(str(non_existent_file))


def test_cleanup_temp_file_logs_error(tmp_path, monkeypatch):
    temp_file = tmp_path / "temp.txt"
    temp_file.write_text("data")

    def boom(path):  # pragma: no cover - raises intentionally
        raise OSError("fail")

    monkeypatch.setattr(os, "unlink", boom)
    cleanup_temp_file(str(temp_file))
    assert temp_file.exists()


@pytest.mark.parametrize(
    "filename, expected_extension",
    [
        ("file.txt", ".txt"),
        ("file.tar.gz", ".gz"),
        ("filename", ".unknown"),
        (".bashrc", ".bashrc"),
        ("no_ext.", "."),
    ],
)
def test_get_file_extension(filename, expected_extension):
    assert get_file_extension(filename) == expected_extension


@pytest.mark.asyncio
async def test_download_from_minio_missing_object_records_error_and_cleanup(monkeypatch):
    object_name = "photos/example.jpg"
    bucket = "bucket"

    monkeypatch.setattr(storage, "file_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(storage.client, "get_object", AsyncMock())
    monkeypatch.setattr(
        storage, "download_file", AsyncMock(side_effect=Exception("boom"))
    )
    monkeypatch.setattr(stats, "record_error", AsyncMock())

    unlink_calls = []

    def fake_unlink(path):
        unlink_calls.append(path)

    monkeypatch.setattr(os, "unlink", fake_unlink)

    with pytest.raises(MinioError):
        await download_from_minio(object_name, bucket, extension=None)

    assert stats.record_error.await_count == 1
    assert stats.record_error.await_args.args[0] == "storage"
    assert len(unlink_calls) == 1
    assert unlink_calls[0].endswith(".jpg")
    storage.client.get_object.assert_not_called()


@pytest.mark.asyncio
async def test_send_group_media_batches_respect_limit(mocker):
    bot = SimpleNamespace(send_media_group=mocker.AsyncMock())
    items = []
    seek_spies = []

    for idx in range(13):
        fh = io.BytesIO(b"data")
        seek_spies.append(mocker.spy(fh, "seek"))
        items.append(
            {
                "file_name": f"file{idx}.jpg",
                "media_type": "photo",
                "file_prefix": "photos/",
                "path": f"photos/file{idx}.jpg",
                "temp_path": f"/tmp/file{idx}.jpg",
                "file_obj": fh,
                "meta": None,
            }
        )

    await send_group_media(bot, 123, items, "Caption")

    assert bot.send_media_group.await_count == 2
    first_call = bot.send_media_group.await_args_list[0].kwargs
    second_call = bot.send_media_group.await_args_list[1].kwargs

    assert len(first_call["media"]) == 10
    assert len(second_call["media"]) == 3

    assert first_call["media"][0].caption == "Caption"
    for media in first_call["media"][1:]:
        assert media.caption is None
    for media in second_call["media"]:
        assert media.caption is None

    for spy in seek_spies:
        assert spy.call_args_list[0].args == (0,)


@pytest.mark.asyncio
async def test_send_group_media_single_item_grouped(mocker):
    bot = SimpleNamespace(send_media_group=mocker.AsyncMock())
    fh = io.BytesIO(b"data")
    items = [
        {
            "file_name": "file.jpg",
            "media_type": "photo",
            "file_prefix": "photos/",
            "path": "photos/file.jpg",
            "temp_path": "/tmp/file.jpg",
            "file_obj": fh,
            "meta": None,
        }
    ]

    await send_group_media(bot, 123, items, "Caption")

    bot.send_media_group.assert_awaited_once()
    sent_call = bot.send_media_group.await_args.kwargs
    media = sent_call["media"]
    assert len(media) == 1
    assert media[0].caption == "Caption"
