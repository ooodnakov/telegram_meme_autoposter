import os

from telegram_auto_poster.utils.general import (
    cleanup_temp_file,
    extract_file_paths,
    extract_filename,
    get_file_extension,
)


def test_extract_filename_with_media_path():
    text = "intro text\nphotos/processed_img.jpg"
    assert extract_filename(text) == "photos/processed_img.jpg"


def test_extract_filename_without_media_path():
    text = "line1\nline2"
    assert extract_filename(text) == "line2"


def test_extract_filename_empty_text():
    assert extract_filename("") is None


def test_extract_file_paths_returns_all_matches():
    text = "photos/a.jpg\nnot-a-path\nvideos/b.mp4"
    assert extract_file_paths(text) == ["photos/a.jpg", "videos/b.mp4"]


def test_extract_file_paths_with_no_matches():
    assert extract_file_paths("just text") == []


def test_cleanup_temp_file_removes_file(tmp_path):
    temp_file = tmp_path / "temp.txt"
    temp_file.write_text("data")
    cleanup_temp_file(str(temp_file))
    assert not temp_file.exists()


def test_cleanup_temp_file_none_path():
    # Should not raise when file_path is None
    cleanup_temp_file(None)


def test_get_file_extension_known():
    assert get_file_extension("file.tar.gz") == ".gz"


def test_get_file_extension_unknown():
    assert get_file_extension("filename") == ".unknown"
