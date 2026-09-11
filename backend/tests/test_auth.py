"""Authentication behaviour tests."""


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_can_register(client):
    response = client.post(
        "/register",
        data={
            "name": "New Student",
            "email": "new@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_invalid_registration_keeps_entered_values(client):
    response = client.post(
        "/register",
        data={
            "name": "New Student",
            "email": "INVALID",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        },
    )

    assert response.status_code == 200
    assert b"Please enter a valid email address" in response.data
    assert b"INVALID" in response.data


def test_user_can_log_in(client, user):
    response = client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_login_rejects_incorrect_password(client, user):
    response = client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 200
    assert b"Incorrect email or password" in response.data


def test_external_next_redirect_is_rejected(client, user):
    response = client.post(
        "/login?next=https://example.org/phishing",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_user_can_log_out(client, user):
    client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
    )

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
