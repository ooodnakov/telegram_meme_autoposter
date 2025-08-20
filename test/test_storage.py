import pytest
from pytest_mock import MockerFixture
from minio.error import MinioException

from telegram_auto_poster.utils.storage import MinioStorage
from telegram_auto_poster.config import BUCKET_MAIN, PHOTOS_PATH


@pytest.fixture
def mock_minio_client(mocker: MockerFixture):
    """Fixture to create a mock Minio client."""
    client = mocker.MagicMock()
    client.bucket_exists = mocker.AsyncMock(return_value=True)
    client.make_bucket = mocker.AsyncMock()
    client.fput_object = mocker.AsyncMock()
    client.fget_object = mocker.AsyncMock()
    client.stat_object = mocker.AsyncMock()
    client.remove_object = mocker.AsyncMock()
    client.list_objects = mocker.AsyncMock(return_value=[])
    client.get_object = mocker.AsyncMock()
    return client


def test_init_storage(mock_minio_client):
    """Test that the Minio client is initialized and buckets are checked."""
    mock_minio_client.bucket_exists.return_value = True
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    mock_minio_client.bucket_exists.assert_called_once_with(BUCKET_MAIN)
    assert storage.client == mock_minio_client


def test_init_storage_bucket_creation(mock_minio_client):
    """Test that a bucket is created if it doesn't exist."""
    mock_minio_client.bucket_exists.return_value = False
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    mock_minio_client.make_bucket.assert_called_once_with(BUCKET_MAIN)


@pytest.mark.asyncio
async def test_store_and_get_submission_metadata(mock_minio_client):
    """Test storing and retrieving submission metadata."""
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    storage.store_submission_metadata(
        "obj1", 123, 456, "photo", message_id=789, media_hash="hash1"
    )
    meta = await storage.get_submission_metadata("obj1")
    assert meta["user_id"] == 123
    assert meta["chat_id"] == 456


@pytest.mark.asyncio
async def test_get_submission_metadata_from_minio(
    mock_minio_client, mocker: MockerFixture
):
    """Test retrieving submission metadata from Minio if not in memory."""
    mock_stat = mocker.MagicMock()
    mock_stat.metadata = {
        "user_id": "123",
        "chat_id": "456",
        "media_type": "photo",
        "message_id": "789",
        "hash": "hash1",
    }
    mock_minio_client.stat_object.return_value = mock_stat
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    # Make get_submission_metadata return None from memory
    storage.submission_metadata = {}
    meta = await storage.get_submission_metadata("obj2")
    mock_minio_client.stat_object.assert_awaited_with(
        bucket_name=BUCKET_MAIN, object_name=f"{PHOTOS_PATH}/obj2"
    )
    assert meta["user_id"] == 123


@pytest.mark.asyncio
async def test_mark_notified(mock_minio_client):
    """Test marking a submission as notified."""
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    storage.store_submission_metadata("obj1", 123, 456, "photo")
    meta = await storage.get_submission_metadata("obj1")
    assert meta["notified"] is False
    storage.mark_notified("obj1")
    meta = await storage.get_submission_metadata("obj1")
    assert meta["notified"] is True


@pytest.mark.asyncio
async def test_upload_file(mock_minio_client, tmp_path):
    """Test uploading a file."""
    file = tmp_path / "test.jpg"
    file.write_text("content")
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    await storage.upload_file(str(file), user_id=123, chat_id=456)
    mock_minio_client.fput_object.assert_awaited_once()
    kwargs = mock_minio_client.fput_object.await_args.kwargs
    assert kwargs["bucket_name"] == BUCKET_MAIN
    assert kwargs["object_name"].startswith(PHOTOS_PATH)
    assert kwargs["metadata"]["user_id"] == "123"


@pytest.mark.asyncio
async def test_download_file(mock_minio_client, tmp_path):
    """Test downloading a file."""
    file = tmp_path / "download.jpg"
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    await storage.download_file("obj1", BUCKET_MAIN, file_path=str(file))
    mock_minio_client.fget_object.assert_awaited_once_with(
        bucket_name=BUCKET_MAIN, object_name="obj1", file_path=str(file)
    )


@pytest.mark.asyncio
async def test_get_object_data(mock_minio_client, mocker: MockerFixture):
    """Test getting object data."""
    mock_response = mocker.MagicMock()
    mock_response.read = mocker.AsyncMock(return_value=b"data")
    mock_response.close = mocker.AsyncMock()
    mock_response.release_conn = mocker.AsyncMock()
    mock_minio_client.get_object.return_value = mock_response
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    data = await storage.get_object_data("obj1", BUCKET_MAIN)
    assert data == b"data"
    mock_response.close.assert_awaited_once()
    mock_response.release_conn.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_object_data_minio_error(mock_minio_client):
    """Test MinioException is raised when getting object data fails."""
    mock_minio_client.get_object.side_effect = MinioException("Failed to get object")
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    with pytest.raises(MinioException):
        await storage.get_object_data("obj1", BUCKET_MAIN)


@pytest.mark.asyncio
async def test_delete_file(mock_minio_client):
    """Test deleting a file."""
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    await storage.delete_file("obj1", BUCKET_MAIN)
    mock_minio_client.remove_object.assert_awaited_once_with(
        bucket_name=BUCKET_MAIN, object_name="obj1"
    )


@pytest.mark.asyncio
async def test_file_exists(mock_minio_client):
    """Test checking if a file exists."""
    storage = MinioStorage(client=mock_minio_client)
    storage._instance = None
    storage._initialized = False
    storage = MinioStorage(client=mock_minio_client)
    await storage.file_exists("obj1", BUCKET_MAIN)
    mock_minio_client.stat_object.assert_awaited_once_with(
        bucket_name=BUCKET_MAIN, object_name="obj1"
    )