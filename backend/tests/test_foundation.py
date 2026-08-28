from app.errors import ErrorCode
from app.models import AdminUser, Policy


def test_health_contract(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["services"]["database"] == "ok"
    assert payload["data"]["services"]["deepseek"] == "not_configured"


def test_csrf_contract(client):
    response = client.get("/api/v1/admin/auth/csrf")
    assert response.status_code == 200
    assert response.get_json()["data"]["csrf_token"]


def test_database_entities_can_be_persisted(app):
    from app.extensions import db

    with app.app_context():
        admin = AdminUser(username="admin", password_hash="hash")
        policy = Policy(code="LEAVE-001", title="休假管理制度", category="休假")
        db.session.add_all([admin, policy])
        db.session.commit()
        assert db.session.scalar(db.select(AdminUser).where(AdminUser.username == "admin")) is not None
        assert db.session.scalar(db.select(Policy).where(Policy.code == "LEAVE-001")) is not None


def test_unknown_api_uses_unified_error_contract(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert payload["error"]["request_id"]

