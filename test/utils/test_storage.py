import pytest

import telegram_auto_poster.utils.storage as storage_module
from telegram_auto_poster.config import BUCKET_MAIN, DOWNLOADS_PATH, PHOTOS_PATH, VIDEOS_PATH
from telegram_auto_poster.utils import db


@pytest.fixture
def storage_instance(tmp_path):
    previous_backend = storage_module.CONFIG.minio.backend
    previous_root = storage_module.CONFIG.minio.garage_root
    previous_public = storage_module.CONFIG.minio.public_url

    storage_module.CONFIG.minio.backend = "garage"
    storage_module.CONFIG.minio.garage_root = str(tmp_path / "garage")
    storage_module.CONFIG.minio.public_url = None
    db.reset_cache_for_tests()
    storage_module.reset_storage_for_tests()
    db.reset_cache_for_tests()
    yield storage_module.storage
    storage_module.CONFIG.minio.backend = previous_backend
    storage_module.CONFIG.minio.garage_root = previous_root
    storage_module.CONFIG.minio.public_url = previous_public
    storage_module.reset_storage_for_tests()
    db.reset_cache_for_tests()


@pytest.mark.asyncio
async def test_store_and_get_submission_metadata(storage_instance):
    await storage_instance.store_submission_metadata(
        "obj1",
        123,
        456,
        "photo",
        message_id=789,
        media_hash="hash1",
        group_id="g1",
        source="src1",
    )
    meta = await storage_instance.get_submission_metadata("obj1")
    assert meta["user_id"] == 123
    assert meta["chat_id"] == 456
    assert meta["group_id"] == "g1"
    assert meta["source"] == "src1"


@pytest.mark.asyncio
async def test_upload_and_download_file(storage_instance, tmp_path):
    source = tmp_path / "sample.txt"
    content = b"hello world"
    source.write_bytes(content)

    assert await storage_instance.upload_file(str(source), object_name="sample.txt")

    target = tmp_path / "out.txt"
    assert await storage_instance.download_file("downloads/sample.txt", BUCKET_MAIN, str(target))
    assert target.read_bytes() == content


@pytest.mark.asyncio
async def test_list_files(storage_instance, tmp_path):
    file_a = tmp_path / "a.jpg"
    file_b = tmp_path / "b.mp4"
    file_a.write_bytes(b"a")
    file_b.write_bytes(b"b")

    await storage_instance.upload_file(str(file_a))
    await storage_instance.upload_file(str(file_b))

    photos = await storage_instance.list_files(BUCKET_MAIN, prefix=PHOTOS_PATH)
    videos = await storage_instance.list_files(BUCKET_MAIN, prefix=VIDEOS_PATH)

    assert any(name.endswith("a.jpg") for name in photos)
    assert any(name.endswith("b.mp4") for name in videos)


@pytest.mark.asyncio
async def test_delete_file(storage_instance, tmp_path):
    file_path = tmp_path / "delete.bin"
    file_path.write_bytes(b"data")
    await storage_instance.upload_file(str(file_path), object_name="delete.bin")

    assert await storage_instance.file_exists("downloads/delete.bin", BUCKET_MAIN)
    await storage_instance.delete_file("downloads/delete.bin", BUCKET_MAIN)
    assert not await storage_instance.file_exists("downloads/delete.bin", BUCKET_MAIN)


@pytest.mark.asyncio
async def test_submission_metadata_normalization(storage_instance):
    object_name = f"{PHOTOS_PATH}/obj3"
    await storage_instance.store_submission_metadata(object_name, 1, 2, "photo")
    meta = await storage_instance.get_submission_metadata("obj3")
    assert meta is not None


@pytest.mark.asyncio
async def test_cache_integration(storage_instance, tmp_path):
    temp_file = tmp_path / "cached.jpg"
    temp_file.write_bytes(b"x")
    await storage_instance.upload_file(str(temp_file))

    # First call populates cache
    await storage_instance.list_files(BUCKET_MAIN)
    # Second call should hit cache without errors
    cached = await storage_instance.list_files(BUCKET_MAIN)
    assert any(name.endswith("cached.jpg") for name in cached)
