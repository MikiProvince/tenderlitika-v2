def test_signup_requires_json_body_not_query_params(client):
    response = client.post("/signup?email=user@example.com&password=StrongPass123")

    assert response.status_code == 422


def test_signup_rejects_invalid_email_before_db_lookup(client):
    response = client.post(
        "/signup",
        json={
            "email": "invalid-email",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email"
