"""Regression checks for removal of the legacy business-alert APIs."""

from app import app


def test_alert_routes_are_removed_and_health_routes_remain():
    routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/api/get_alerts" not in routes
    assert "/api/ai_status" not in routes
    assert "/api/me/alerts" not in routes

    assert "/api/get_health" in routes
    assert "/api/chart/health" in routes
    assert "/api/me/health" in routes
    assert "/api/sensor" in routes
