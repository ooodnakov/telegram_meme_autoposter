import json


def test_telegram_analytics_history_is_paginated(auth_client, mocker):
    snapshots = [{"fetched_at": "2026-09-20T10:00:00+00:00", "channels": []}]
    mocker.patch(
        "telegram_auto_poster.web.app.get_channel_analytics_history_count",
        return_value=3,
    )
    history = mocker.patch(
        "telegram_auto_poster.web.app.get_channel_analytics_history",
        return_value=snapshots,
    )

    response = auth_client.get(
        "/api/stats/telegram/history", params={"page": 2, "per_page": 2}
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": snapshots,
        "page": 2,
        "per_page": 2,
        "total_items": 3,
        "total_pages": 2,
    }
    history.assert_awaited_once_with(offset=2, limit=2)


def test_telegram_analytics_history_export_downloads_every_snapshot(
    auth_client, mocker
):
    snapshots = [{"fetched_at": "2026-09-20T10:00:00+00:00", "channels": []}]
    history = mocker.patch(
        "telegram_auto_poster.web.app.get_channel_analytics_history",
        return_value=snapshots,
    )
    count = mocker.patch(
        "telegram_auto_poster.web.app.get_channel_analytics_history_count",
        return_value=1,
    )

    response = auth_client.get("/api/stats/telegram/history/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="telegram-analytics-'
    )
    assert json.loads(response.content)["snapshots"] == snapshots
    count.assert_awaited_once_with()
    history.assert_awaited_once_with(offset=0, limit=1)
