from __future__ import annotations

import re

from flask import Blueprint, g, request

from ..auth import employee_required
from ..errors import ApiError, ErrorCode, success
from ..services.chat import (
    conversation_detail,
    create_conversation,
    delete_conversation,
    get_answer,
    list_conversations,
    refresh_answer,
    replay_answer,
    serialize_answer,
    submit_question,
)


chat_bp = Blueprint("chat", __name__)
CLIENT_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def client_session_id() -> str:
    employee = getattr(g, "employee_user", None)
    if employee is not None:
        return f"employee-{employee.id}"
    value = request.headers.get("X-Client-Session-ID", "").strip()
    if not CLIENT_SESSION_RE.fullmatch(value):
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "X-Client-Session-ID 必须为 8 到 64 位字母、数字、下划线或连字符",
            400,
            {"header": "X-Client-Session-ID"},
        )
    return value


@chat_bp.post("/chat/query")
@employee_required
def query():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    answer = submit_question(client_session_id(), payload)
    return success(serialize_answer(answer))


@chat_bp.post("/chat/replay")
@employee_required
def replay():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    answer, changes = replay_answer(client_session_id(), payload)
    return success(
        serialize_answer(answer),
        meta={"previous_answer_id": payload["answer_id"], "scenario_changes": changes},
    )


@chat_bp.get("/conversations")
@employee_required
def conversations():
    return success(list_conversations(client_session_id()))


@chat_bp.post("/conversations")
@employee_required
def new_conversation():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    conversation = create_conversation(client_session_id(), payload.get("title"))
    return success(
        {
            "id": conversation.id,
            "title": conversation.title,
            "scenario": conversation.scenario_state,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
        },
        status=201,
    )


@chat_bp.get("/conversations/<conversation_id>")
@employee_required
def get_conversation(conversation_id: str):
    return success(conversation_detail(conversation_id, client_session_id()))


@chat_bp.delete("/conversations/<conversation_id>")
@employee_required
def remove_conversation(conversation_id: str):
    delete_conversation(conversation_id, client_session_id())
    return success({"deleted": True, "conversation_id": conversation_id})


@chat_bp.get("/answers/<answer_id>")
@employee_required
def answer_detail(answer_id: str):
    return success(serialize_answer(get_answer(answer_id, client_session_id())))


@chat_bp.post("/answers/<answer_id>/refresh")
@employee_required
def refresh(answer_id: str):
    answer, meta = refresh_answer(client_session_id(), answer_id)
    return success(serialize_answer(answer), meta=meta)
