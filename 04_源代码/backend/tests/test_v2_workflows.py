from __future__ import annotations

import hashlib
from datetime import date

from app.extensions import db
from app.models import Clause, Policy, PolicyGapScan, PolicyVersion, QueryLog
from app.services.indexing import rebuild_index
from app.services.policy_gaps import latest_policy_gap_scan, run_policy_gap_scan, serialize_scan


HEADERS = {"X-Client-Session-ID": "v2-client-0001"}


def seed_policy(app):
    with app.app_context():
        policy = Policy(code="V2-TRAVEL", title="差旅报销制度", category="差旅")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id, version="2.0", effective_date=date(2026, 8, 29), status="active",
            file_name="travel.md", file_path="travel.md", mime_type="text/markdown", size_bytes=200,
            file_sha256="d" * 64,
        )
        db.session.add(version)
        db.session.flush()
        text = "员工应在出差结束后 10 个工作日内提交报销申请、发票和行程凭证，由部门负责人审批。"
        db.session.add(Clause(
            policy_version_id=version.id, stable_anchor="v2-travel-1", section_path="报销流程",
            clause_number="第一条", text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(), token_count=len(text),
        ))
        db.session.commit()
        rebuild_index()


def test_reverse_questions_collect_conditions_then_return_checklist(client, app):
    seed_policy(app)
    def generator(question, _history, evidence):
        missing = []
        if "出差范围=" not in question:
            missing.append("出差范围")
        if "票据是否齐全=" not in question:
            missing.append("票据是否齐全")
        return {
            "decision": "conditional" if missing else "allowed",
            "conclusion": "条件不足，暂时无法判断" if missing else "可以",
            "claims": [{"text": evidence[0]["quote"], "evidence_ids": [evidence[0]["id"]]}],
            "next_steps": [] if missing else [{"text": "在出差结束后 10 个工作日内提交报销申请、发票和行程凭证。", "evidence_ids": [evidence[0]["id"]]}],
            "missing_conditions": missing,
        }
    app.config["ANSWER_GENERATOR"] = generator
    first = client.post("/api/v1/chat/query", headers=HEADERS, json={"question": "我想办理差旅报销，怎么办？"}).get_json()["data"]
    assert first["status"] == "clarification"
    assert first["clarification"]["slot"] == "travel_scope"
    assert [item["field"] for item in first["scenario_form"]] == ["travel_scope"]

    second = client.post("/api/v1/chat/replay", headers=HEADERS, json={
        "answer_id": first["answer_id"], "scenario": {**first["scenario"], "travel_scope": "domestic"},
    }).get_json()["data"]
    assert second["status"] == "clarification"
    assert second["clarification"]["slot"] == "has_invoice"
    assert [item["field"] for item in second["scenario_form"]] == ["travel_scope", "has_invoice"]

    final = client.post("/api/v1/chat/replay", headers=HEADERS, json={
        "answer_id": second["answer_id"], "scenario": {**second["scenario"], "has_invoice": True},
    }).get_json()["data"]
    assert final["status"] == "answer"
    assert final["decision"] == "allowed" and final["conclusion"] == "可以"
    assert final["checklist"]["materials"]
    assert final["checklist"]["materials"][0]["evidence_ids"]
    assert all(item["answered"] for item in final["scenario_form"])


def test_policy_gap_scan_persists_ai_findings(app):
    seed_policy(app)
    with app.app_context():
        db.session.add(QueryLog(question="陪产假如何办理？", result_status="refusal", hit_count=0))
        db.session.commit()
        app.config["POLICY_GAP_GENERATOR"] = lambda dataset: {
            "summary": "发现陪产假制度缺失。",
            "issues": [{
                "category": "missing_policy", "severity": "high", "title": "陪产假制度缺失",
                "description": "问答记录存在未覆盖事项。", "suggested_action": "补充陪产假制度并重建索引。",
                "occurrences": 1, "evidence_refs": [next(item["ref"] for item in dataset["questions"] if "陪产假" in item["question"])],
            }],
        }
        scan = run_policy_gap_scan("manual")
        data = serialize_scan(scan)
        assert data["status"] == "completed" and data["model_name"]
        assert data["issues"][0]["category"] == "missing_policy"
        assert data["issues"][0]["evidence"][0]["question"] == "陪产假如何办理？"
        assert db.session.scalar(db.select(db.func.count()).select_from(PolicyGapScan)) == 1
        assert latest_policy_gap_scan(run_if_due=True).id == scan.id
