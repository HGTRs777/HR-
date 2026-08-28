from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import g, session

from .errors import ApiError, ErrorCode
from .extensions import db
from .models import AdminUser


F = TypeVar("F", bound=Callable[..., Any])


def current_admin() -> AdminUser | None:
    user_id = session.get("admin_user_id")
    if not isinstance(user_id, int):
        return None
    user = db.session.get(AdminUser, user_id)
    return user if user and user.is_active else None


def admin_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_admin()
        if not user:
            session.pop("admin_user_id", None)
            raise ApiError(ErrorCode.AUTH_REQUIRED, "请先登录管理员账号", 401)
        g.admin_user = user
        return view(*args, **kwargs)

    return cast(F, wrapped)
