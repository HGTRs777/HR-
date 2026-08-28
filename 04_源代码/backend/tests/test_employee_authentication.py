from __future__ import annotations

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AdminUser, EmployeeUser


def _challenge(client) -> tuple[str, int]:
    payload = client.get("/api/v1/auth/human-challenge").get_json()["data"]
    return payload["challenge_id"], payload["target_position"]


def test_employee_login_requires_one_time_human_challenge(app):
    with app.app_context():
        employee = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        assert employee is not None
        employee.password_hash = generate_password_hash("88888888")
        db.session.commit()

    client = app.test_client()
    challenge_id, _position = _challenge(client)
    wrong = client.post(
        "/api/v1/employee/auth/login",
        json={"username": "test-staff", "password": "88888888", "challenge_id": challenge_id, "slider_position": 0},
    )
    assert wrong.status_code == 400

    challenge_id, position = _challenge(client)
    logged_in = client.post(
        "/api/v1/employee/auth/login",
        json={"username": "test-staff", "password": "88888888", "challenge_id": challenge_id, "slider_position": position},
    )
    assert logged_in.status_code == 200
    assert logged_in.get_json()["data"]["employee"]["username"] == "test-staff"
    assert client.get("/api/v1/conversations").status_code == 200
    assert client.post("/api/v1/employee/auth/logout").status_code == 200
    assert client.get("/api/v1/conversations").status_code == 401


def test_admin_login_also_requires_human_challenge(app):
    with app.app_context():
        db.session.add(AdminUser(username="admin", password_hash=generate_password_hash("88888888")))
        db.session.commit()

    client = app.test_client()
    challenge_id, position = _challenge(client)
    logged_in = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "admin", "password": "88888888", "challenge_id": challenge_id, "slider_position": position},
    )
    assert logged_in.status_code == 200
    assert logged_in.get_json()["data"]["admin"]["username"] == "admin"
