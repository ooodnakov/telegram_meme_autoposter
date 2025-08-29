import os
from unittest.mock import AsyncMock

import pytest
from telegram_auto_poster.utils.general import (
    MinioError,
    cleanup_temp_file,
    download_from_minio,
    extract_file_paths,
    extract_filename,
    get_file_extension,
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
        ("   ", []),
    ],
)
def test_extract_file_paths(text, expected):
    assert extract_file_paths(text) == expected


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
        storage.client, "fget_object", AsyncMock(side_effect=Exception("boom"))
    )

    async def fake_download(object_name, bucket, file_path):
        await storage.client.fget_object(
            bucket_name=bucket, object_name=object_name, file_path=file_path
        )

    monkeypatch.setattr(storage, "download_file", fake_download)
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
