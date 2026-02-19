def test_health_check_returns_alive(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "Tenderlitika V2 is alive"}
