from flask import Blueprint, request, session
from werkzeug.security import check_password_hash

from ..auth import admin_required, current_admin
from ..errors import ApiError, ErrorCode, success
from ..extensions import db
from ..models import AdminUser, utcnow
from ..security import issue_csrf_token


security_bp = Blueprint("security", __name__)


@security_bp.get("/csrf")
def csrf():
    return success({"csrf_token": issue_csrf_token()})


@security_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not username or not password:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "用户名和密码不能为空", 400)
    user = db.session.scalar(db.select(AdminUser).where(AdminUser.username == username))
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        raise ApiError(ErrorCode.AUTH_REQUIRED, "用户名或密码错误", 401)
    session.clear()
    session["admin_user_id"] = user.id
    user.last_login_at = utcnow()
    db.session.commit()
    return success({"authenticated": True, "admin": {"id": user.id, "username": user.username}, "csrf_token": issue_csrf_token()})


@security_bp.post("/logout")
@admin_required
def logout():
    session.clear()
    return success({"authenticated": False})


@security_bp.get("/session")
def auth_session():
    user = current_admin()
    return success(
        {
            "authenticated": user is not None,
            "admin": {"id": user.id, "username": user.username} if user else None,
        }
    )
