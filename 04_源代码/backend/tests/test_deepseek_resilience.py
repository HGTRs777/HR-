from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import Clause, EmployeeUser, Policy, PolicyVersion
from app.services import deepseek as deepseek_service
from app.services.deepseek import ModelGenerationError
from app.services.indexing import rebuild_index


def _seed_policy(app) -> None:
    text = "员工累计工作满 1 年不满 10 年的，每年享受 5 天年假；年假应提前 5 个工作日申请。"
    with app.app_context():
        policy = Policy(code="DEEPSEEK-RESILIENCE", title="年假测试制度", category="测试")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 31),
            status="active",
            file_name="resilience.md",
            file_path="resilience.md",
            mime_type="text/markdown",
            size_bytes=len(text.encode()),
            file_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(Clause(
            policy_version_id=version.id,
            stable_anchor="deepseek-resilience-1",
            section_path="年假",
            clause_number="第一条",
            text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            token_count=len(text),
        ))
        employee = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        employee.employee_status = "regular"
        employee.tenure_years = 3
        employee.annual_leave_entitlement = 5
        db.session.commit()
        rebuild_index()


def _answer_generator(_question, _history, evidence):
    return {
        "decision": "allowed",
        "conclusion": "可以",
        "primary_answer": "你今年可享受 5 天年假。",
        "claims": [{"text": "你今年可享受 5 天年假。", "evidence_ids": [evidence[0]["id"]]}],
        "next_steps": [],
        "missing_conditions": [],
    }


def test_first_second_and_multi_turn_questions_keep_legal_plain_text_history(client, app):
    _seed_policy(app)
    classifier_calls: list[tuple[str, list[dict[str, str]]]] = []

    def classifier(question, history):
        classifier_calls.append((question, history))
        return {"question_type": "quota" if "几天" in question else "procedure", "answer_focus": "年假主答案"}

    app.config["QUESTION_CLASSIFIER"] = classifier
    app.config["ANSWER_GENERATOR"] = _answer_generator
    first = client.post("/api/v1/chat/query", json={"question": "我今年有几天年假？"}).get_json()["data"]
    second = client.post("/api/v1/chat/query", json={
        "conversation_id": first["conversation_id"], "question": "那怎么申请？",
    }).get_json()["data"]

    assert first["status"] == second["status"] == "answer"
    assert len(classifier_calls) == 2 and classifier_calls[0][1] == []
    second_history = classifier_calls[1][1]
    assert [item["role"] for item in second_history] == ["user", "assistant"]
    assert all(isinstance(item["content"], str) for item in second_history)
    assert all(not item["content"].lstrip().startswith("{") for item in second_history)
    assert second["conversation_id"] == first["conversation_id"] and second["evidence"]


def test_intent_api_failure_uses_local_fallback_and_main_answer_continues(client, app):
    _seed_policy(app)
    app.config["QUESTION_CLASSIFIER"] = lambda *_args: (_ for _ in ()).throw(TimeoutError("classifier timeout"))
    app.config["ANSWER_GENERATOR"] = _answer_generator

    data = client.post("/api/v1/chat/query", json={"question": "我今年有几天年假？"}).get_json()["data"]

    assert data["status"] == "answer" and data["degraded"] is False
    assert data["question_type"] == "quota"
    assert "5 天" in data["primary_answer"] and data["evidence"]


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class _FakeStatusError(RuntimeError):
    def __init__(self, status_code: int, message: str = "temporary error"):
        super().__init__(message)
        self.status_code = status_code


class _FakeResponses:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _FakeResponse(outcome)


class _FakeClient:
    def __init__(self, outcomes):
        self.responses = _FakeResponses(outcomes)


@pytest.mark.parametrize("status_code", [429, 503])
def test_temporary_http_error_retries_and_then_succeeds(app, monkeypatch, status_code):
    client = _FakeClient([
        _FakeStatusError(status_code),
        json.dumps({"question_type": "deadline", "answer_focus": "报销截止时间"}, ensure_ascii=False),
    ])
    factories = []
    monkeypatch.setattr(deepseek_service, "OpenAI", lambda **kwargs: factories.append(kwargs) or client)
    monkeypatch.setattr(deepseek_service.time, "sleep", lambda _seconds: None)
    app.config.update(DEEPSEEK_API_KEY="sk-test-retry-key", DEEPSEEK_MAX_RETRIES=2)

    with app.app_context():
        result = deepseek_service.classify_question_intent("最晚什么时候报销？", [])

    assert result.question_type == "deadline"
    assert len(client.responses.calls) == 2 and len(factories) == 1
    assert factories[0]["max_retries"] == 0


def test_malformed_json_200_response_is_retried(app, monkeypatch):
    invalid = '{"decision":"allowed","conclusion":"可以","primary_answer":"按"累计工龄"计算为5天","claims":[]}'
    valid = json.dumps({
        "decision": "allowed", "conclusion": "可以", "primary_answer": "你今年可享受 5 天年假。",
        "claims": [{"text": "你今年可享受 5 天年假。", "evidence_ids": ["evidence-1"]}],
        "next_steps": [], "missing_conditions": [],
    }, ensure_ascii=False)
    client = _FakeClient([invalid, valid])
    monkeypatch.setattr(deepseek_service, "OpenAI", lambda **_kwargs: client)
    monkeypatch.setattr(deepseek_service.time, "sleep", lambda _seconds: None)
    app.config.update(DEEPSEEK_API_KEY="sk-test-json-key", DEEPSEEK_MAX_RETRIES=2)

    with app.app_context():
        result = deepseek_service.generate_structured_answer(
            "年假几天？", [], [{"id": "evidence-1", "quote": "每年享受 5 天年假。"}],
            question_type="quota", answer_focus="年假天数",
        )

    assert "5 天" in result.primary_answer and len(client.responses.calls) == 2


def test_primary_answer_uses_evidence_bound_first_claim_when_duplicate_field_differs():
    generated = deepseek_service.GeneratedAnswer.model_validate({
        "decision": "allowed",
        "conclusion": "可以",
        "primary_answer": "模型重复字段中的不同措辞。",
        "claims": [{"text": "首条声明是唯一可信主答案。", "evidence_ids": ["evidence-1"]}],
        "next_steps": [],
        "missing_conditions": [],
    })
    assert generated.primary_answer == generated.claims[0].text


def test_deadline_focus_does_not_request_workflow_only_conditions(app):
    from app.services.chat import _clarification_for, _missing_condition_labels

    scenario = {"matter_type": "annual_leave", "employee_status": "regular", "tenure_years": 3}
    with app.app_context():
        clarification = _clarification_for("那最晚什么时候申请？", scenario, "deadline")
        missing = _missing_condition_labels("那最晚什么时候申请？", scenario, clarification, "deadline")
    assert clarification is None and missing == []


def test_all_llm_stages_share_one_client_and_one_model(app, monkeypatch):
    intent = json.dumps({"question_type": "general", "answer_focus": "制度信息"}, ensure_ascii=False)
    answer = json.dumps({
        "decision": "informational", "conclusion": "需要", "primary_answer": "需要查阅制度。",
        "claims": [{"text": "需要查阅制度。", "evidence_ids": ["evidence-1"]}],
        "next_steps": [], "missing_conditions": [],
    }, ensure_ascii=False)
    gap = json.dumps({"summary": "未发现问题", "issues": []}, ensure_ascii=False)
    client = _FakeClient([intent, answer, gap])
    factories = []
    monkeypatch.setattr(deepseek_service, "OpenAI", lambda **kwargs: factories.append(kwargs) or client)
    app.config.update(DEEPSEEK_API_KEY="sk-one-client-key", DEEPSEEK_MODEL="deepseek-v4-flash")

    with app.app_context():
        deepseek_service.classify_question_intent("制度是什么？", [])
        deepseek_service.generate_structured_answer(
            "制度是什么？", [], [{"id": "evidence-1", "quote": "需要查阅制度。"}],
        )
        deepseek_service.generate_policy_gap_analysis({"policies": [], "questions": [], "feedback": []})

    assert len(factories) == 1
    assert {call["model"] for call in client.responses.calls} == {"deepseek-v4-flash"}
    assert factories[0]["base_url"] == app.config["DEEPSEEK_BASE_URL"]
    assert factories[0]["timeout"] == app.config["DEEPSEEK_TIMEOUT_SECONDS"]


@pytest.mark.parametrize(
    ("status_code", "category", "retryable"),
    [
        (400, "bad_request", False), (401, "authentication_error", False),
        (402, "insufficient_balance", False), (422, "parameter_error", False),
        (429, "rate_limited", True), (500, "service_error", True), (503, "service_busy", True),
    ],
)
def test_http_errors_are_classified_without_exposing_api_key(app, caplog, status_code, category, retryable):
    app.config["DEEPSEEK_API_KEY"] = "sk-never-log-this-secret"
    with app.app_context():
        error = deepseek_service._model_error(
            "question_intent", _FakeStatusError(status_code, "failed sk-never-log-this-secret"),
        )
    assert error.status_code == status_code and error.category == category and error.retryable is retryable
    assert "sk-never-log-this-secret" not in str(error)


def test_true_answer_api_failure_returns_specific_friendly_message(client, app):
    _seed_policy(app)
    app.config["QUESTION_CLASSIFIER"] = lambda *_args: {"question_type": "quota", "answer_focus": "年假天数"}
    app.config["ANSWER_GENERATOR"] = lambda *_args: (_ for _ in ()).throw(ModelGenerationError(
        "invalid credentials",
        stage="answer_generation",
        category="authentication_error",
        status_code=401,
        exception_type="AuthenticationError",
        user_message="AI 服务认证失败，请联系管理员检查 API Key。",
    ))

    data = client.post("/api/v1/chat/query", json={"question": "年假有几天？"}).get_json()["data"]

    assert data["status"] == "degraded" and data["degraded"] is True
    assert "认证失败" in data["primary_answer"]
    assert data["degraded_reason"] == "answer_generation:authentication_error:401"
    assert data["claims"] == [] and data["evidence"]
