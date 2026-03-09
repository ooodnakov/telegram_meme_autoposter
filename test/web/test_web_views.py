from __future__ import annotations

from unittest.mock import call

from fastapi.testclient import TestClient

from telegram_auto_poster.config import PHOTOS_PATH
from telegram_auto_poster.utils.timezone import parse_to_utc_timestamp
from telegram_auto_poster.web.app import MANUAL_SCHEDULE_INTERVAL_SECONDS


def test_dashboard_api_payload(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app._get_dashboard_payload",
        new=mocker.AsyncMock(
            return_value={
                "suggestions_count": 1,
                "batch_count": 2,
                "posts_count": 3,
                "trash_count": 4,
                "scheduled_count": 5,
                "next_scheduled_at": None,
                "daily": {"media_received": 10},
                "recent_events": [],
            }
        ),
    )
    resp = auth_client.get("/api/dashboard")
    assert resp.status_code == 200
    assert resp.json()["batch_count"] == 2


def test_jobs_api_lists_jobs(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app.job_manager.list_jobs",
        new=mocker.AsyncMock(
            return_value=[
                {
                    "name": "ocr_missing_images",
                    "title": "OCR missing images",
                    "description": "Extract OCR text for stored images.",
                    "status": "idle",
                    "status_detail": None,
                    "current_run_started_at": None,
                    "current_run_duration_seconds": None,
                    "current_stats": {},
                    "last_run_started_at": None,
                    "last_run_finished_at": None,
                    "last_run_duration_seconds": None,
                    "last_run_status": None,
                    "last_run_stats": {},
                    "last_error": None,
                    "can_run": True,
                    "runtime": {
                        "can_run": True,
                        "ocr_enabled": True,
                        "languages": "eng+rus",
                        "tesseract_available": True,
                        "tesseract_version": "5.3.0",
                        "tesseract_error": None,
                    },
                }
            ]
        ),
    )

    resp = auth_client.get("/api/jobs")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"][0]["name"] == "ocr_missing_images"
    assert payload["items"][0]["runtime"]["languages"] == "eng+rus"


def test_jobs_api_runs_job(mocker, auth_client: TestClient):
    run_job = mocker.patch(
        "telegram_auto_poster.web.app.job_manager.run_job",
        new=mocker.AsyncMock(
            return_value={
                "name": "ocr_missing_images",
                "title": "OCR missing images",
                "description": "Extract OCR text for stored images.",
                "status": "running",
                "status_detail": "Preparing run",
                "current_run_started_at": "2026-03-08T10:00:00+00:00",
                "current_run_duration_seconds": 1.0,
                "current_stats": {"images_missing_ocr": 10},
                "last_run_started_at": None,
                "last_run_finished_at": None,
                "last_run_duration_seconds": None,
                "last_run_status": None,
                "last_run_stats": {},
                "last_error": None,
                "can_run": False,
                "runtime": {"can_run": True},
            }
        ),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post("/api/jobs/ocr_missing_images/run", json={})
    assert resp.status_code == 202
    assert resp.json()["status"] == "running"
    run_job.assert_awaited_once_with("ocr_missing_images")
    record.assert_awaited_once()


def test_jobs_api_pauses_job(mocker, auth_client: TestClient):
    pause_job = mocker.patch(
        "telegram_auto_poster.web.app.job_manager.pause_job",
        new=mocker.AsyncMock(
            return_value={
                "name": "ocr_missing_images",
                "title": "OCR missing images",
                "description": "Extract OCR text for stored images.",
                "status": "paused",
                "status_detail": "Paused",
                "pause_requested": True,
                "current_run_started_at": "2026-03-08T10:00:00+00:00",
                "current_run_duration_seconds": 10.0,
                "current_stats": {"images_missing_ocr": 10},
                "last_run_started_at": None,
                "last_run_finished_at": None,
                "last_run_duration_seconds": None,
                "last_run_status": None,
                "last_run_stats": {},
                "last_error": None,
                "can_run": False,
                "can_pause": False,
                "can_resume": True,
                "runtime": {"can_run": True},
            }
        ),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post("/api/jobs/ocr_missing_images/pause", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    pause_job.assert_awaited_once_with("ocr_missing_images")
    record.assert_awaited_once()


def test_jobs_api_resumes_job(mocker, auth_client: TestClient):
    resume_job = mocker.patch(
        "telegram_auto_poster.web.app.job_manager.resume_job",
        new=mocker.AsyncMock(
            return_value={
                "name": "ocr_missing_images",
                "title": "OCR missing images",
                "description": "Extract OCR text for stored images.",
                "status": "running",
                "status_detail": "Resuming",
                "pause_requested": False,
                "current_run_started_at": "2026-03-08T10:00:00+00:00",
                "current_run_duration_seconds": 10.0,
                "current_stats": {"images_missing_ocr": 10},
                "last_run_started_at": None,
                "last_run_finished_at": None,
                "last_run_duration_seconds": None,
                "last_run_status": None,
                "last_run_stats": {},
                "last_error": None,
                "can_run": False,
                "can_pause": True,
                "can_resume": False,
                "runtime": {"can_run": True},
            }
        ),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post("/api/jobs/ocr_missing_images/resume", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    resume_job.assert_awaited_once_with("ocr_missing_images")
    record.assert_awaited_once()


def test_queue_api_lists_posts(mocker, auth_client: TestClient):
    async def fake_get_meta(name):
        assert name == "processed.jpg"
        return {"caption": "caption", "source": "@src"}

    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts_count",
        return_value=1,
    )
    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts",
        return_value=[("scheduled/processed.jpg", 1)],
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        new=mocker.AsyncMock(return_value="http://example.com/media.jpg"),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_submission_metadata",
        side_effect=fake_get_meta,
    )

    resp = auth_client.get("/api/queue")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_items"] == 1
    assert payload["items"][0]["url"] == "http://example.com/media.jpg"
    assert payload["items"][0]["caption"] == "caption"


def test_posts_api_filters_items_and_returns_filter_metadata(
    mocker, auth_client: TestClient
):
    mocker.patch(
        "telegram_auto_poster.web.app._collect_post_summary_groups",
        new=mocker.AsyncMock(
            return_value=[
                {
                    "items": [
                        {
                            "path": "photos/processed_cat.jpg",
                            "name": "processed_cat.jpg",
                            "kind": "image",
                            "caption": "Funny cat",
                            "source": "@cats",
                            "_search_text": "processed_cat.jpg funny cat @cats",
                        }
                    ],
                    "count": 1,
                    "is_group": False,
                    "caption": "Funny cat",
                    "source": "@cats",
                    "_search_text": "processed_cat.jpg funny cat @cats",
                },
                {
                    "items": [
                        {
                            "path": "videos/processed_dog.mp4",
                            "name": "processed_dog.mp4",
                            "kind": "video",
                            "caption": "Loud dog",
                            "source": "@dogs",
                            "_search_text": "processed_dog.mp4 loud dog @dogs bark bark",
                        },
                        {
                            "path": "videos/processed_dog_2.mp4",
                            "name": "processed_dog_2.mp4",
                            "kind": "video",
                            "caption": "Loud dog 2",
                            "source": "@dogs",
                            "_search_text": "processed_dog_2.mp4 loud dog 2 @dogs",
                        },
                    ],
                    "count": 2,
                    "is_group": True,
                    "caption": "Loud dog",
                    "source": "@dogs",
                    "_search_text": "processed_dog.mp4 loud dog @dogs bark bark processed_dog_2.mp4 loud dog 2",
                },
            ]
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._hydrate_post_groups",
        new=mocker.AsyncMock(
            side_effect=lambda groups: [
                {key: value for key, value in group.items() if key != "_search_text"}
                for group in groups
            ]
        ),
    )

    resp = auth_client.get(
        "/api/posts",
        params={
            "q": "bark",
            "kind": "video",
            "layout": "group",
            "source": "@dogs",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_items"] == 1
    assert [item["source"] for item in payload["items"]] == ["@dogs"]
    assert payload["filters"] == {
        "q": "bark",
        "kind": "video",
        "layout": "group",
        "source": "@dogs",
        "sources": ["@cats", "@dogs"],
    }


def test_posts_api_ignores_invalid_filter_values(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app._collect_post_summary_groups",
        new=mocker.AsyncMock(
            return_value=[
                {
                    "items": [
                        {
                            "path": "photos/processed_cat.jpg",
                            "name": "processed_cat.jpg",
                            "kind": "image",
                            "caption": "Funny cat",
                            "source": "@cats",
                            "_search_text": "processed_cat.jpg funny cat @cats",
                        }
                    ],
                    "count": 1,
                    "is_group": False,
                    "caption": "Funny cat",
                    "source": "@cats",
                    "_search_text": "processed_cat.jpg funny cat @cats",
                }
            ]
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._hydrate_post_groups",
        new=mocker.AsyncMock(
            side_effect=lambda groups: [
                {key: value for key, value in group.items() if key != "_search_text"}
                for group in groups
            ]
        ),
    )

    resp = auth_client.get(
        "/api/posts",
        params={"kind": "bad", "layout": "bad", "source": "all"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_items"] == 1
    assert payload["filters"]["kind"] == "all"
    assert payload["filters"]["layout"] == "all"
    assert payload["filters"]["source"] == "all"


def test_action_api_push_group(mocker, auth_client: TestClient):
    group = mocker.patch(
        "telegram_auto_poster.web.app._push_post_group",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_metas_for_paths",
        new=mocker.AsyncMock(return_value=[]),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post(
        "/api/actions",
        json={
            "action": "push",
            "origin": "posts",
            "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    group.assert_awaited_once_with([f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"])
    record.assert_awaited_once()


def test_batch_send_processes_posts(mocker, auth_client: TestClient):
    posts = [
        {"items": [{"path": f"{PHOTOS_PATH}/batch_a.jpg"}]},
        {"items": [{"path": f"{PHOTOS_PATH}/batch_b.jpg"}]},
    ]
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=posts),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_metas_for_paths",
        new=mocker.AsyncMock(return_value=[]),
    )
    push_group = mocker.patch(
        "telegram_auto_poster.web.app._push_post_group",
        new=mocker.AsyncMock(),
    )
    decr = mocker.patch(
        "telegram_auto_poster.web.app.decrement_batch_count",
        new=mocker.AsyncMock(),
    )
    rec = mocker.patch(
        "telegram_auto_poster.web.app.stats.record_batch_sent",
        new=mocker.AsyncMock(),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post("/api/batch/send", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "processed_groups": 1}
    assert push_group.await_args_list == [
        call([f"{PHOTOS_PATH}/batch_a.jpg", f"{PHOTOS_PATH}/batch_b.jpg"]),
    ]
    assert decr.await_args_list == [call(2)]
    assert rec.await_args_list == [call(1)]
    record.assert_not_awaited()


def test_manual_schedule_api_schedules_paths(mocker, auth_client: TestClient):
    schedule = mocker.patch(
        "telegram_auto_poster.web.app._schedule_post_at",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_metas_for_paths",
        new=mocker.AsyncMock(
            return_value=[
                (f"{PHOTOS_PATH}/a.jpg", {}),
                (f"{PHOTOS_PATH}/b.jpg", {}),
            ]
        ),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post(
        "/api/batch/manual-schedule",
        json={
            "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
            "scheduled_at": "2024-01-01 12:00",
            "origin": "batch",
        },
    )
    base_ts = parse_to_utc_timestamp("2024-01-01 12:00")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "scheduled": 2}
    assert schedule.await_args_list == [
        call(f"{PHOTOS_PATH}/a.jpg", base_ts),
        call(
            f"{PHOTOS_PATH}/b.jpg",
            base_ts + MANUAL_SCHEDULE_INTERVAL_SECONDS,
        ),
    ]
    record.assert_awaited_once()


def test_reset_endpoints_return_json(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app.clear_event_history",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.reset_daily_stats",
        new=mocker.AsyncMock(return_value="Daily statistics have been reset."),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.reset_leaderboard",
        new=mocker.AsyncMock(return_value="Leaderboard reset."),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.force_save",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    assert auth_client.post("/api/events/reset", json={}).json() == {"status": "ok"}
    assert auth_client.post("/api/stats/reset", json={}).json() == {
        "status": "ok",
        "message": "Daily statistics have been reset.",
    }
    assert auth_client.post("/api/leaderboard/reset", json={}).json() == {
        "status": "ok",
        "message": "Leaderboard reset.",
    }
