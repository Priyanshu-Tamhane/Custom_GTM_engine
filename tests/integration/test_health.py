"""Integration tests for health and readiness endpoints."""

from app.api.routes.health import health_check, readiness_check


def test_health_check_function():
    data = health_check()
    assert data["status"] == "healthy"
    assert data["service"] == "GTM Intelligence Engine"
    assert "version" in data
    assert "timestamp" in data


def test_readiness_check_function():
    response = readiness_check()
    assert response.status_code in (200, 503)
    data = response.body.decode()
    assert "database" in data
    assert "redis" in data
