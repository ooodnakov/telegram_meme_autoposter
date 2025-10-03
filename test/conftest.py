import atexit
import os
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from pydantic import SecretStr

CONFIG_CONTENT = """
[Telegram]
api_id = 1
api_hash = test
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = bot
bot_chat_id = 1
[Chats]
selected_chats = @test1,@test2
luba_chat = @luba
[Web]
session_secret = secret
"""

CONFIG_PATH = Path("/tmp/test_config.ini")
CONFIG_PATH.write_text(CONFIG_CONTENT, encoding="utf-8")

os.environ.setdefault("CONFIG_PATH", str(CONFIG_PATH))
os.environ.setdefault("VALKEY_BACKEND", "valkey")
os.environ.setdefault("MINIO_BACKEND", "garage")

CACHE_DIR = Path.home() / ".cache" / "telegram-auto-poster"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CARGO_BIN = Path.home() / ".cargo" / "bin"
if CARGO_BIN.exists():
    os.environ["PATH"] = f"{CARGO_BIN}:{os.environ.get('PATH', '')}"

def _worker_identity() -> tuple[str, int]:
    env_worker = os.environ.get("PYTEST_XDIST_WORKER")
    worker_count = os.environ.get("PYTEST_XDIST_WORKER_COUNT")

    if env_worker:
        worker_id = env_worker
    elif worker_count:
        worker_id = "controller"
    else:
        worker_id = "main"

    digits = "".join(ch for ch in worker_id if ch.isdigit())
    index = int(digits or "0")
    return worker_id, index


WORKER_ID, WORKER_INDEX = _worker_identity()
XDIST_CONTROLLER = WORKER_ID == "controller"
PORT_OFFSET = WORKER_INDEX * 10

VALKEY_PORT = int(os.environ.get("VALKEY_PORT", 9401 + PORT_OFFSET))
VALKEY_HOST = "127.0.0.1"

GARAGE_S3_PORT = int(os.environ.get("GARAGE_S3_PORT", 3900 + PORT_OFFSET))
GARAGE_RPC_PORT = int(os.environ.get("GARAGE_RPC_PORT", 3901 + PORT_OFFSET))
GARAGE_ADMIN_PORT = int(os.environ.get("GARAGE_ADMIN_PORT", 3903 + PORT_OFFSET))
GARAGE_WEB_PORT = int(os.environ.get("GARAGE_WEB_PORT", 3902 + PORT_OFFSET))
GARAGE_K2V_PORT = int(os.environ.get("GARAGE_K2V_PORT", 3904 + PORT_OFFSET))
GARAGE_HOST = "127.0.0.1"
GARAGE_REGION = "garage"
GARAGE_RUNTIME_DIR = CACHE_DIR / f"garage-runtime-{WORKER_ID}"

os.environ.setdefault("VALKEY_HOST", VALKEY_HOST)
os.environ.setdefault("VALKEY_PORT", str(VALKEY_PORT))
os.environ.setdefault("VALKEY_PASS", "")
os.environ.setdefault("MINIO_URL", f"http://{GARAGE_HOST}:{GARAGE_S3_PORT}")
os.environ.setdefault("MINIO_REGION", GARAGE_REGION)
os.environ.setdefault("MINIO_ACCESS_KEY", "garage")
os.environ.setdefault("MINIO_SECRET_KEY", "garage")


def _wait_for_port(host: str, port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {host}:{port}")


def _ensure_valkey_binary() -> Path:
    env_path = os.environ.get("VALKEY_SERVER_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    backend = os.environ.get("VALKEY_BACKEND", "valkey")
    if backend == "pogocache":
        return _ensure_pogocache_binary()

    binary = shutil.which("valkey-server") or shutil.which("redis-server")
    if not binary:
        raise RuntimeError(
            "valkey-server binary not found. Install valkey-server or provide VALKEY_SERVER_PATH."
        )
    return Path(binary)


def _ensure_pogocache_binary() -> Path:
    env_path = os.environ.get("POGOCACHE_SERVER_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    binary = shutil.which("pogocache")
    if not binary:
        raise RuntimeError(
            "pogocache binary not found. Install pogocache or provide POGOCACHE_SERVER_PATH."
        )
    return Path(binary)


def _ensure_garage_binary() -> Path:
    binary = shutil.which("garage")
    if binary:
        return Path(binary)

    cargo = shutil.which("cargo")
    if not cargo:
        raise RuntimeError("cargo is required to install Garage")

    subprocess.run([cargo, "install", "garage", "--locked"], check=True)

    binary = shutil.which("garage")
    if not binary:
        raise RuntimeError("garage binary not found after installation")
    return Path(binary)


def _garage_cmd(
    binary: Path, config_path: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), "-c", str(config_path), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _garage_node_id(binary: Path, config_path: Path) -> str:
    for _ in range(120):
        result = _garage_cmd(binary, config_path, "node", "id", check=False)
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip()
            return raw.split("@", 1)[0]
        time.sleep(0.5)
    raise RuntimeError("Failed to retrieve Garage node ID")


def _garage_create_key(
    binary: Path, config_path: Path, bucket: str, name: str
) -> tuple[str, str]:
    result = _garage_cmd(binary, config_path, "key", "create", name)
    key_id = secret = None
    for line in result.stdout.splitlines():
        if line.startswith("Key ID:"):
            key_id = line.split(":", 1)[1].strip()
        elif line.startswith("Secret key:"):
            secret = line.split(":", 1)[1].strip()
    if not key_id or not secret:
        raise RuntimeError("Unable to parse Garage key credentials")

    _garage_cmd(
        binary,
        config_path,
        "bucket",
        "allow",
        "--read",
        "--write",
        "--owner",
        bucket,
        "--key",
        key_id,
    )
    return key_id, secret


def _start_valkey() -> dict[str, object]:
    backend = os.environ.get("VALKEY_BACKEND", "valkey")
    binary = _ensure_valkey_binary()

    if backend == "pogocache":
        args = [str(binary), "-h", VALKEY_HOST, "-p", str(VALKEY_PORT)]
    else:
        args = [
            str(binary),
            "--port",
            str(VALKEY_PORT),
            "--bind",
            VALKEY_HOST,
            "--save",
            "",
            "--appendonly",
            "no",
            "--daemonize",
            "no",
        ]

    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_port(VALKEY_HOST, VALKEY_PORT)
    return {"process": process, "host": VALKEY_HOST, "port": VALKEY_PORT}


def _start_garage() -> dict[str, object]:
    binary = _ensure_garage_binary()
    work_dir = GARAGE_RUNTIME_DIR
    existing_config = work_dir / "garage.toml"
    pkill_binary = shutil.which("pkill")
    if existing_config.exists() and pkill_binary:
        subprocess.run(
            [pkill_binary, "-f", str(existing_config)],
            check=False,
        )
        time.sleep(0.2)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    metadata_dir = work_dir / "meta"
    data_dir = work_dir / "data"
    work_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    config = f"""metadata_dir = \"{metadata_dir}\"\ndata_dir = \"{data_dir}\"\ndb_engine = \"sqlite\"\n\nreplication_factor = 1\n\nrpc_bind_addr = \"{GARAGE_HOST}:{GARAGE_RPC_PORT}\"\nrpc_public_addr = \"{GARAGE_HOST}:{GARAGE_RPC_PORT}\"\nrpc_secret = \"{secrets.token_hex(32)}\"\n\n[s3_api]\ns3_region = \"{GARAGE_REGION}\"\napi_bind_addr = \"{GARAGE_HOST}:{GARAGE_S3_PORT}\"\nroot_domain = \".s3.garage.localhost\"\n\n[s3_web]\nbind_addr = \"{GARAGE_HOST}:{GARAGE_WEB_PORT}\"\nroot_domain = \".web.garage.localhost\"\nindex = \"index.html\"\n\n[k2v_api]\napi_bind_addr = \"{GARAGE_HOST}:{GARAGE_K2V_PORT}\"\n\n[admin]\napi_bind_addr = \"{GARAGE_HOST}:{GARAGE_ADMIN_PORT}\"\nadmin_token = \"{secrets.token_urlsafe(32)}\"\nmetrics_token = \"{secrets.token_urlsafe(32)}\"\n"""
    config_path = work_dir / "garage.toml"
    config_path.write_text(config, encoding="utf-8")

    process = subprocess.Popen(
        [str(binary), "-c", str(config_path), "server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_port(GARAGE_HOST, GARAGE_RPC_PORT)
        time.sleep(1.0)

        node_id = _garage_node_id(binary, config_path)

        for command in (
            ("layout", "assign", "-z", "local", "-c", "1G", node_id),
            ("layout", "apply", "--version", "1"),
        ):
            last_error = ""
            max_attempts = 15
            for attempt in range(1, max_attempts + 1):
                result = _garage_cmd(binary, config_path, *command, check=False)
                if result.returncode == 0:
                    break

                last_error = (result.stdout + result.stderr).strip()
                time.sleep(0.3 * attempt)
            else:
                raise RuntimeError(
                    "Garage command failed after retries: "
                    f"{' '.join(command)} -> {last_error or 'no output'}"
                )

        _wait_for_port(GARAGE_HOST, GARAGE_S3_PORT)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise

    from telegram_auto_poster.config import BUCKET_MAIN

    create_result = _garage_cmd(
        binary, config_path, "bucket", "create", BUCKET_MAIN, check=False
    )
    if create_result.returncode:
        message = (create_result.stdout + create_result.stderr).lower()
        if "already exists" not in message:
            create_result.check_returncode()

    access_key, secret_key = _garage_create_key(
        binary, config_path, BUCKET_MAIN, "testsuite"
    )

    return {
        "process": process,
        "host": GARAGE_HOST,
        "s3_port": GARAGE_S3_PORT,
        "rpc_port": GARAGE_RPC_PORT,
        "config_path": config_path,
        "access_key": access_key,
        "secret_key": secret_key,
        "region": GARAGE_REGION,
        "url": f"http://{GARAGE_HOST}:{GARAGE_S3_PORT}",
    }


if XDIST_CONTROLLER:
    CONFIG = None  # type: ignore[assignment]
    db = None  # type: ignore[assignment]
    reset_storage_for_tests = None  # type: ignore[assignment]

    VALKEY_INFO = {
        "process": None,
        "host": VALKEY_HOST,
        "port": VALKEY_PORT,
    }
    GARAGE_INFO = {
        "process": None,
        "host": GARAGE_HOST,
        "s3_port": GARAGE_S3_PORT,
        "rpc_port": GARAGE_RPC_PORT,
        "config_path": None,
        "access_key": "",
        "secret_key": "",
        "region": GARAGE_REGION,
        "url": f"http://{GARAGE_HOST}:{GARAGE_S3_PORT}",
    }

    def _reset_cache_for_tests_wrapper() -> None:  # pragma: no cover - controller only
        return

    def _reset_storage_for_tests_wrapper() -> None:  # pragma: no cover - controller only
        return
else:
    VALKEY_INFO = _start_valkey()
    GARAGE_INFO = _start_garage()

    os.environ["MINIO_ACCESS_KEY"] = GARAGE_INFO["access_key"]
    os.environ["MINIO_SECRET_KEY"] = GARAGE_INFO["secret_key"]

    from telegram_auto_poster.config import CONFIG  # noqa: E402
    from telegram_auto_poster.utils import db  # noqa: E402
    from telegram_auto_poster.utils.storage import reset_storage_for_tests  # noqa: E402

    CONFIG.valkey.backend = os.environ.get("VALKEY_BACKEND", "valkey")
    CONFIG.valkey.host = VALKEY_INFO["host"]
    CONFIG.valkey.port = VALKEY_INFO["port"]
    CONFIG.valkey.password = SecretStr("")

    CONFIG.minio.backend = "garage"
    CONFIG.minio.url = GARAGE_INFO["url"]
    CONFIG.minio.host = GARAGE_INFO["host"]
    CONFIG.minio.port = GARAGE_INFO["s3_port"]
    CONFIG.minio.access_key = SecretStr(GARAGE_INFO["access_key"])
    CONFIG.minio.secret_key = SecretStr(GARAGE_INFO["secret_key"])
    CONFIG.minio.region = GARAGE_INFO["region"]
    CONFIG.minio.public_url = None

    db.reset_cache_for_tests()
    reset_storage_for_tests()

    def _reset_cache_for_tests_wrapper() -> None:
        db.reset_cache_for_tests()

    def _reset_storage_for_tests_wrapper() -> None:
        reset_storage_for_tests()


def _stop_process(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _shutdown_services() -> None:
    for info in (VALKEY_INFO, GARAGE_INFO):
        proc = info.get("process")
        if isinstance(proc, subprocess.Popen):
            _stop_process(proc)


atexit.register(_shutdown_services)


@pytest.fixture(autouse=True)
def clean_datastores():
    if XDIST_CONTROLLER:
        yield
        return

    _reset_cache_for_tests_wrapper()
    _reset_storage_for_tests_wrapper()
    yield
    _reset_cache_for_tests_wrapper()
    _reset_storage_for_tests_wrapper()


@pytest.fixture
def mock_config(mocker):
    from telegram_auto_poster.config import (
        BotConfig,
        ChatsConfig,
        Config,
        TelegramConfig,
        WebConfig,
    )

    mocker.patch(
        "telegram_auto_poster.config.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1,
                api_hash="test",
                username="test",
                target_channels=["@test"],
            ),
            bot=BotConfig(
                bot_token="token",
                bot_username="bot",
                bot_chat_id=1,
                admin_ids=[1],
            ),
            web=WebConfig(session_secret="secret"),
            chats=ChatsConfig(
                selected_chats=["@test1", "@test2"],
                luba_chat="@luba",
            ),
        ),
    )
