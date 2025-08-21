from loguru import logger
from telegram_auto_poster.utils.telemetry import init_telemetry


def test_init_telemetry_no_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    init_telemetry(logger)


def test_init_telemetry_with_endpoint(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
    init_telemetry(logger)
