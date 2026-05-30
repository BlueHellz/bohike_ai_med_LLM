"""Verify README-documented REST endpoints are mounted on the app."""

from app.main import app

DOCUMENTED_ROUTES = {
    ("POST", "/api/v1/sessions"),
    ("POST", "/api/v1/sessions/{session_id}/messages"),
    ("GET", "/api/v1/sessions/{session_id}/status"),
    ("POST", "/api/v1/sessions/{session_id}/close"),
    ("POST", "/api/v1/surgeon/query"),
    ("POST", "/api/v1/surgeon/pre-op"),
    ("POST", "/api/v1/surgeon/post-op"),
    ("GET", "/api/v1/physician/alerts"),
    ("POST", "/api/v1/physician/alerts/{alert_id}/ack"),
    ("GET", "/api/v1/physician/sessions/flagged"),
    ("GET", "/api/v1/physician/session/{session_id}/layer"),
    ("GET", "/api/v1/physician/session/{session_id}/messages"),
    ("POST", "/api/v1/physician/session/{session_id}/override"),
    ("GET", "/api/v1/patients/{patient_id}/profile"),
    ("PUT", "/api/v1/patients/{patient_id}/profile"),
}


def _mounted_routes():
    routes = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path:
            for method in methods:
                if method != "HEAD":
                    routes.add((method, path))
    return routes


def test_documented_routes_are_mounted():
    mounted = _mounted_routes()
    missing = DOCUMENTED_ROUTES - mounted
    assert not missing, f"Missing documented routes: {sorted(missing)}"


def test_health_endpoint():
    mounted = _mounted_routes()
    assert ("GET", "/health") in mounted
