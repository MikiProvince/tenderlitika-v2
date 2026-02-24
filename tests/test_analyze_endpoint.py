from types import SimpleNamespace

import main as app_module


def test_analyze_requires_api_key(client):
    response = client.post(
        "/analyze",
        json={
            "text": "Tender text " * 10,
            "cost_price": 100000,
            "planned_margin_percent": 10,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-API-Key"


def test_analyze_returns_expected_payload_with_overrides(client, monkeypatch):
    fake_user = SimpleNamespace(id=77, plan="free")
    fake_db = object()
    captured = {}

    def override_db():
        yield fake_db

    app_module.app.dependency_overrides[app_module.get_db] = override_db
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: fake_user

    monkeypatch.setattr(app_module, "check_monthly_quota", lambda db, user: None)
    monkeypatch.setattr(
        app_module,
        "extract_tender_data",
        lambda text, llm_provider=None: {"nmck": 120000.0, "payment_terms_days": 30},
    )
    monkeypatch.setattr(
        app_module,
        "find_danger_phrases",
        lambda text: [{"title": "Danger", "severity": "high"}],
    )
    monkeypatch.setattr(app_module, "calculate_risk", lambda extracted: (3, "low", ["reason"]))
    monkeypatch.setattr(app_module, "calculate_financials", lambda extracted, cost, margin: (12.34, 5000.0))
    monkeypatch.setattr(app_module, "calculate_safe_cost_price", lambda extracted: 95000.0)

    class FakeRow:
        id = 123

    def fake_save_analysis(**kwargs):
        captured.update(kwargs)
        return FakeRow()

    monkeypatch.setattr(app_module, "save_analysis", fake_save_analysis)

    response = client.post(
        "/analyze",
        json={
            "text": "Tender text " * 10,
            "cost_price": 100000,
            "planned_margin_percent": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["analysis_id"] == 123
    assert data["risk_score"] == 3
    assert data["safe_cost_price"] == 95000.0
    assert "danger_phrases" in data["extracted_data"]

    assert captured["db"] is fake_db
    assert captured["user_id"] == 77
