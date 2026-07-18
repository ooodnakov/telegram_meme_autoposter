from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from telegram_auto_poster.web.app import (
    SPA_PUBLIC_PATHS,
    SPA_PUBLIC_PREFIXES,
    _is_spa_public_path,
    app,
)


EXPECTED_PUBLIC_PATHS = {
    "/login",
    "/auth",
    "/logout",
    "/language",
    "/favicon.ico",
    "/robots.txt",
    "/placeholder.svg",
}
EXPECTED_PUBLIC_PREFIXES = ("/assets/",)
SENSITIVE_PREFIXES = (
    "/api",
    "/action",
    "/batch",
    "/queue",
    "/trash",
    "/events",
    "/stats",
    "/leaderboard",
    "/settings",
    "/jobs",
    "/debug",
    "/admin",
    "/pydoc",
)


def test_spa_public_paths_are_limited_to_login_auth_language_and_safe_assets():
    assert SPA_PUBLIC_PATHS == EXPECTED_PUBLIC_PATHS
    assert SPA_PUBLIC_PREFIXES == EXPECTED_PUBLIC_PREFIXES


@pytest.mark.parametrize("path", sorted(EXPECTED_PUBLIC_PATHS))
def test_is_spa_public_path_allows_only_explicit_safe_public_files(path: str):
    assert _is_spa_public_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/assets/index.js",
        "/assets/nested/chunk.css",
    ],
)
def test_is_spa_public_path_allows_frontend_static_assets(path: str):
    assert _is_spa_public_path(path) is True


@pytest.mark.parametrize("prefix", SENSITIVE_PREFIXES)
def test_sensitive_prefixes_are_not_public(prefix: str):
    assert _is_spa_public_path(prefix) is False
    assert _is_spa_public_path(f"{prefix}/anything") is False


@pytest.mark.parametrize(
    "path",
    [
        "/assets-for-admin/secret.js",
        "/api/session",
        "/api/debug/state",
        "/debug/vars",
        "/admin/users",
        "/pydoc/telegram_auto_poster.web.app",
    ],
)
def test_similar_or_debug_paths_are_not_public(path: str):
    assert _is_spa_public_path(path) is False


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/login"),
        ("GET", "/auth"),
        ("GET", "/logout"),
        ("POST", "/language"),
        ("GET", "/favicon.ico"),
        ("GET", "/robots.txt"),
        ("GET", "/placeholder.svg"),
        ("GET", "/assets/nonexistent.js"),
    ],
)
def test_public_routes_are_reachable_without_admin_session(method: str, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == "/assets":
            route.app.config_checked = True

    with TestClient(app) as client:
        resp = client.request(method, path, follow_redirects=False)

    assert resp.status_code != 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/session",
        "/api/dashboard",
        "/api/debug/state",
        "/debug/vars",
        "/admin/users",
        "/pydoc/telegram_auto_poster.web.app",
    ],
)
def test_dashboard_api_and_debug_like_routes_require_admin_session(path: str):
    with TestClient(app) as client:
        resp = client.get(path, follow_redirects=False)

    if path.startswith("/api/"):
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}
    else:
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
