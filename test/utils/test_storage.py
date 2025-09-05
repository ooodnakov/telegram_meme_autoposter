import pytest
from miniopy_async.error import MinioException
from pytest_mock import MockerFixture
from telegram_auto_poster.config import BUCKET_MAIN, PHOTOS_PATH
from telegram_auto_poster.utils.db import _redis_key


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


class FakeRedis:
    def __init__(self):
        self.store: dict[str, dict[str, str]] = {}

    async def hset(self, key, field=None, value=None, mapping=None):
        if mapping is not None:
            self.store.setdefault(key, {}).update(mapping)
        elif field is not None and value is not None:
            self.store.setdefault(key, {})[field] = value
        else:
            raise ValueError("hset requires field and value or mapping")

    async def hgetall(self, key):
        return self.store.get(key, {}).copy()


@pytest.fixture
def mock_redis_client() -> FakeRedis:
    return FakeRedis()


@pytest.fixture(autouse=True)
def patch_redis_client(mocker: MockerFixture, mock_redis_client: FakeRedis):
    mocker.patch(
        "telegram_auto_poster.utils.storage.get_async_redis_client",
        return_value=mock_redis_client,
    )


@pytest.fixture
def storage_factory(mock_minio_client):
    """Factory to create a clean MinioStorage instance."""

    def _create():
        from telegram_auto_poster.utils.storage import MinioStorage as StorageClass

        StorageClass._instance = None
        StorageClass._initialized = False
        return StorageClass(client=mock_minio_client)

    return _create


@pytest.fixture
def storage(storage_factory):
    """Provides a MinioStorage instance for each test."""
    storage_instance = storage_factory()
    yield storage_instance
    from telegram_auto_poster.utils.storage import MinioStorage as StorageClass

    StorageClass._instance = None
    StorageClass._initialized = False


def test_init_storage(storage, mock_minio_client):
    """Test that the Minio client is initialized and buckets are checked."""
    mock_minio_client.bucket_exists.assert_called_once_with(BUCKET_MAIN)
    assert storage.client == mock_minio_client


def test_init_storage_bucket_creation(mock_minio_client, storage_factory):
    """Test that a bucket is created if it doesn't exist."""
    mock_minio_client.bucket_exists.return_value = False
    storage_factory()
    mock_minio_client.make_bucket.assert_called_once_with(BUCKET_MAIN)


@pytest.mark.asyncio
async def test_store_and_get_submission_metadata(storage):
    """Test storing and retrieving submission metadata."""
    await storage.store_submission_metadata(
        "obj1",
        123,
        456,
        "photo",
        message_id=789,
        media_hash="hash1",
        group_id="g1",
        source="src1",
    )
    meta = await storage.get_submission_metadata("obj1")
    assert meta["user_id"] == 123
    assert meta["chat_id"] == 456
    assert meta["group_id"] == "g1"
    assert meta["source"] == "src1"


@pytest.mark.asyncio
async def test_get_submission_metadata_normalizes_prefix(storage):
    """Return metadata when only the basename is provided."""
    object_name = f"{PHOTOS_PATH}/obj3"
    await storage.store_submission_metadata(object_name, 1, 2, "photo")
    meta = await storage.get_submission_metadata("obj3")
    assert meta is not None


@pytest.mark.asyncio
async def test_get_submission_metadata_from_redis(
    storage, mock_minio_client, mock_redis_client
):
    """Metadata is retrieved from Redis when not in memory."""
    await storage.store_submission_metadata(
        "obj_redis",
        111,
        222,
        "photo",
        message_id=333,
        media_hash="hash2",
        group_id="g2",
        source="src2",
    )
    # Clear in-memory cache to force Redis lookup
    storage.submission_metadata = {}
    meta = await storage.get_submission_metadata("obj_redis")
    assert meta["user_id"] == 111
    assert meta["chat_id"] == 222
    assert meta["group_id"] == "g2"
    mock_minio_client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_get_submission_metadata_missing(storage, mock_minio_client):
    """Return ``None`` when metadata is absent in memory and Valkey."""
    storage.submission_metadata = {}
    meta = await storage.get_submission_metadata("obj2")
    assert meta is None
    mock_minio_client.stat_object.assert_not_called()


@pytest.mark.asyncio
async def test_mark_notified(storage, mock_redis_client):
    """Test marking a submission as notified."""
    await storage.store_submission_metadata("obj1", 123, 456, "photo")
    meta = await storage.get_submission_metadata("obj1")
    assert meta["notified"] is False
    await storage.mark_notified("obj1")
    meta = await storage.get_submission_metadata("obj1")
    assert meta["notified"] is True
    data = await mock_redis_client.hgetall(_redis_key("submissions", "obj1"))
    assert data["notified"] == "1"


@pytest.mark.asyncio
async def test_upload_file(storage, mock_minio_client, tmp_path):
    """Test uploading a file."""
    file = tmp_path / "test.jpg"
    file.write_text("content")
    await storage.upload_file(
        str(file), user_id=123, chat_id=456, group_id="g3", source="src3"
    )
    mock_minio_client.fput_object.assert_awaited_once()
    kwargs = mock_minio_client.fput_object.await_args.kwargs
    assert kwargs["bucket_name"] == BUCKET_MAIN
    assert kwargs["object_name"].startswith(PHOTOS_PATH)
    assert "metadata" not in kwargs
    meta = storage.submission_metadata[kwargs["object_name"]]
    assert meta["user_id"] == 123
    assert meta["group_id"] == "g3"
    assert meta["source"] == "src3"


@pytest.mark.asyncio
async def test_download_file(storage, mock_minio_client, tmp_path):
    """Test downloading a file."""
    file = tmp_path / "download.jpg"
    await storage.download_file("obj1", BUCKET_MAIN, file_path=str(file))
    mock_minio_client.fget_object.assert_awaited_once_with(
        bucket_name=BUCKET_MAIN, object_name="obj1", file_path=str(file)
    )


@pytest.mark.asyncio
async def test_get_object_data(storage, mock_minio_client, mocker: MockerFixture):
    """Test getting object data."""
    mock_response = mocker.MagicMock()
    mock_response.read = mocker.AsyncMock(return_value=b"data")
    mock_response.close = mocker.AsyncMock()
    mock_response.release_conn = mocker.AsyncMock()
    mock_minio_client.get_object.return_value = mock_response
    data = await storage.get_object_data("obj1", BUCKET_MAIN)
    assert data == b"data"
    mock_response.close.assert_awaited_once()
    mock_response.release_conn.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_object_data_minio_error(storage, mock_minio_client):
    """Test MinioException is raised when getting object data fails."""
    mock_minio_client.get_object.side_effect = MinioException("Failed to get object")
    with pytest.raises(MinioException):
        await storage.get_object_data("obj1", BUCKET_MAIN)


@pytest.mark.asyncio
async def test_delete_file(storage, mock_minio_client):
    """Test deleting a file."""
    await storage.delete_file("obj1", BUCKET_MAIN)
    mock_minio_client.remove_object.assert_awaited_once_with(
        bucket_name=BUCKET_MAIN, object_name="obj1"
    )


@pytest.mark.asyncio
async def test_file_exists(storage, mock_minio_client):
    """Test checking if a file exists."""
    await storage.file_exists("obj1", BUCKET_MAIN)
    mock_minio_client.stat_object.assert_awaited_once_with(
        bucket_name=BUCKET_MAIN, object_name="obj1"
    )
