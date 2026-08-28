from flask import Blueprint, request, session
from werkzeug.security import check_password_hash

from ..auth import admin_required, current_admin, current_employee, employee_required
from ..errors import ApiError, ErrorCode, success
from ..extensions import db
from ..models import AdminUser, EmployeeUser, utcnow
from ..security import issue_csrf_token, issue_human_challenge, verify_human_challenge


security_bp = Blueprint("security", __name__)
employee_security_bp = Blueprint("employee_security", __name__)
human_security_bp = Blueprint("human_security", __name__)


@human_security_bp.get("/human-challenge")
def human_challenge():
    return success(issue_human_challenge())


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
    verify_human_challenge(payload)
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


@employee_security_bp.post("/login")
def employee_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not username or not password:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "用户名和密码不能为空", 400)
    verify_human_challenge(payload)
    user = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == username))
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        raise ApiError(ErrorCode.AUTH_REQUIRED, "用户名或密码错误", 401)
    session.clear()
    session["employee_user_id"] = user.id
    user.last_login_at = utcnow()
    db.session.commit()
    return success(
        {
            "authenticated": True,
            "employee": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "department": user.department,
            },
        }
    )


@employee_security_bp.post("/logout")
@employee_required
def employee_logout():
    session.clear()
    return success({"authenticated": False})


@employee_security_bp.get("/session")
def employee_auth_session():
    user = current_employee()
    return success(
        {
            "authenticated": user is not None,
            "employee": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "department": user.department,
            }
            if user
            else None,
        }
    )
