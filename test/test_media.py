import os

import pytest
from PIL import Image
from pytest_mock import MockerFixture
from telegram_auto_poster.media.photo import add_watermark_to_image
from telegram_auto_poster.media.video import add_watermark_to_video
from telegram_auto_poster.utils.general import MinioError


@pytest.fixture
def sample_image(tmpdir):
    """Fixture to create a sample image file"""
    img = Image.new("RGB", (200, 200), color="blue")
    path = os.path.join(tmpdir, "sample.jpg")
    img.save(path)
    return path


@pytest.fixture
def sample_video(tmpdir):
    """Fixture to create a sample video file"""
    path = os.path.join(tmpdir, "sample.mp4")
    with open(path, "wb") as f:
        f.write(os.urandom(1024))
    return path


@pytest.mark.asyncio
async def test_add_watermark_to_image(mocker, sample_image):
    """Test that a watermark is added and the image is uploaded."""
    mock_storage = mocker.patch("telegram_auto_poster.media.photo.storage")
    mock_storage.get_submission_metadata = mocker.AsyncMock(
        return_value={
            "user_id": 123,
            "chat_id": 456,
            "message_id": 789,
        }
    )
    mock_storage.upload_file = mocker.AsyncMock(return_value=True)
    mock_piexif_dump = mocker.patch("piexif.dump", return_value=b"")

    await add_watermark_to_image(sample_image, "output.jpg", media_hash="some_hash")

    # Check that upload_file was called with the correct arguments
    from telegram_auto_poster.config import BUCKET_MAIN, PHOTOS_PATH

    mock_storage.upload_file.assert_awaited_once()
    call_args = mock_storage.upload_file.await_args.args
    assert call_args[1] == BUCKET_MAIN
    assert call_args[2] == f"{PHOTOS_PATH}/output.jpg"
    call_kwargs = mock_storage.upload_file.await_args.kwargs
    assert call_kwargs["user_id"] == 123
    assert call_kwargs["chat_id"] == 456
    assert call_kwargs["message_id"] == 789
    assert call_kwargs["media_hash"] == "some_hash"

    # Check that the EXIF data was correct
    mock_piexif_dump.assert_called_once()
    exif_data = mock_piexif_dump.call_args[0][0]
    assert exif_data["0th"][270] == "t.me/ooodnakov_memes"  # ImageDescription
    assert exif_data["0th"][315] == "t.me/ooodnakov_memes"  # Artist
    assert exif_data["0th"][33432] == "t.me/ooodnakov_memes"  # Copyright


@pytest.mark.asyncio
async def test_add_watermark_to_image_upload_failure(mocker, sample_image):
    """Ensure an error is raised if upload to MinIO fails."""
    mock_storage = mocker.patch("telegram_auto_poster.media.photo.storage")
    mock_storage.get_submission_metadata = mocker.AsyncMock(return_value=None)
    mock_storage.upload_file = mocker.AsyncMock(return_value=False)
    mocker.patch("piexif.dump", return_value=b"")

    with pytest.raises(MinioError):
        await add_watermark_to_image(sample_image, "output.jpg")


@pytest.mark.asyncio
async def test_probe_video_size(sample_video):
    """Test that video dimensions are probed correctly."""
    # This test requires ffprobe to be installed
    from telegram_auto_poster.media.video import _probe_video_size

    try:
        width, height = await _probe_video_size(sample_video)
        assert isinstance(width, int)
        assert isinstance(height, int)
    except FileNotFoundError:
        pytest.skip("ffprobe not found, skipping test")


@pytest.mark.asyncio
async def test_add_watermark_to_video_ffmpeg_error(mocker: MockerFixture, sample_video):
    """Test that an error is raised if ffmpeg fails."""
    mocker.patch("telegram_auto_poster.media.video.storage")
    mocker.patch(
        "telegram_auto_poster.media.video._probe_video_size",
        return_value=(1920, 1080),
    )

    mock_ffmpeg = mocker.AsyncMock()
    mock_ffmpeg.communicate = mocker.AsyncMock(return_value=(b"", b"ffmpeg error"))
    mock_ffmpeg.returncode = 1
    mocker.patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_ffmpeg,
    )

    with pytest.raises(RuntimeError, match="ffmpeg error"):
        await add_watermark_to_video(sample_video, "output.mp4")


@pytest.mark.asyncio
async def test_add_watermark_to_video(mocker: MockerFixture, sample_video):
    """Test that a watermark is added to a video and uploaded."""
    mock_storage = mocker.patch("telegram_auto_poster.media.video.storage")
    mock_storage.get_submission_metadata = mocker.AsyncMock(
        return_value={
            "user_id": 123,
            "chat_id": 456,
            "message_id": 789,
        }
    )
    mock_storage.upload_file = mocker.AsyncMock(return_value=True)

    mock_probe = mocker.patch(
        "telegram_auto_poster.media.video._probe_video_size",
        return_value=(1920, 1080),
    )

    mock_ffmpeg = mocker.AsyncMock()
    mock_ffmpeg.communicate = mocker.AsyncMock(return_value=(b"", b""))
    mock_ffmpeg.returncode = 0
    mocker.patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_ffmpeg,
    )

    await add_watermark_to_video(sample_video, "output.mp4", media_hash="some_hash")

    # Check that upload_file was called with the correct arguments
    from telegram_auto_poster.config import BUCKET_MAIN, VIDEOS_PATH

    mock_storage.upload_file.assert_awaited_once()
    call_args = mock_storage.upload_file.await_args.args
    assert call_args[1] == BUCKET_MAIN
    assert call_args[2] == f"{VIDEOS_PATH}/output.mp4"
    call_kwargs = mock_storage.upload_file.await_args.kwargs
    assert call_kwargs["user_id"] == 123
    assert call_kwargs["chat_id"] == 456
    assert call_kwargs["message_id"] == 789
    assert call_kwargs["media_hash"] == "some_hash"


@pytest.mark.asyncio
async def test_add_watermark_to_video_upload_failure(
    mocker: MockerFixture, sample_video
):
    """Ensure an error is raised if upload to MinIO fails."""
    mock_storage = mocker.patch("telegram_auto_poster.media.video.storage")
    mock_storage.get_submission_metadata = mocker.AsyncMock(return_value=None)
    mock_storage.upload_file = mocker.AsyncMock(return_value=False)
    mocker.patch(
        "telegram_auto_poster.media.video._probe_video_size",
        return_value=(1920, 1080),
    )
    mock_ffmpeg = mocker.AsyncMock()
    mock_ffmpeg.communicate = mocker.AsyncMock(return_value=(b"", b""))
    mock_ffmpeg.returncode = 0
    mocker.patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_ffmpeg,
    )

    with pytest.raises(MinioError):
        await add_watermark_to_video(sample_video, "output.mp4")
