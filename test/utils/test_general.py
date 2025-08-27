import pytest
from telegram_auto_poster.utils.general import (
    cleanup_temp_file,
    extract_file_paths,
    extract_filename,
    get_file_extension,
)


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
