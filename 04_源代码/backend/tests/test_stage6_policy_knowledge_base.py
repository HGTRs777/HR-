import json
from io import BytesIO
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app.demo_policy_catalog import (
    DISCLAIMER,
    LIBRARY_NAME,
    POLICY_CATALOG,
    catalog_clause_count,
    render_policy,
)
from app.extensions import db
from app.models import Clause, Policy, PolicyVersion
from app.services.chunking import split_clauses
from app.services.file_parser import parse_document
from app.services.policies import create_policy_version, update_policy_version
from app.services.retrieval import hybrid_search


REQUIRED_CATEGORIES = {
    "入职管理", "试用期与转正", "考勤", "漏打卡补卡", "休假", "加班调休", "差旅", "报销",
    "薪酬", "福利", "培训", "调岗", "离职", "部门专项", "信息安全",
}
REQUIRED_FIELDS = (
    "知识库标识：", "使用声明：", "制度名称：", "制度编号：", "生效日期：", "适用对象：", "适用部门：",
    "资格条件：", "排除条件：", "时间限制：", "次数 / 天数 / 金额上限：", "所需材料：", "办理步骤：",
    "提交对象：", "审批角色：", "HR处理角色：", "对应条款正文：",
)


def test_catalog_is_explicitly_simulated_structured_and_within_target_size():
    assert LIBRARY_NAME == "实训模拟企业 HR 制度知识库"
    assert "不代表任何真实企业" in DISCLAIMER
    assert len(POLICY_CATALOG) == 15
    assert {item["category"] for item in POLICY_CATALOG} == REQUIRED_CATEGORIES
    assert 100 <= catalog_clause_count() <= 150
    assert catalog_clause_count() == 122
    for spec in POLICY_CATALOG:
        rendered = render_policy(spec)
        blocks, _mime = parse_document(spec["filename"], rendered.encode("utf-8"))
        clauses = split_clauses(blocks, spec["code"], spec["version"])
        assert len(clauses) == len(spec["rules"])
        assert all(field in clause.text for clause in clauses for field in REQUIRED_FIELDS)
        assert all(LIBRARY_NAME in clause.text and DISCLAIMER in clause.text for clause in clauses)


def test_seed_keeps_old_version_and_activates_new_catalog_version(app):
    with app.app_context():
        old_text = "# 旧考勤制度\n\n第一条 旧版模拟规则。"
        policy = create_policy_version(
            {"code": "ATTEND-001", "title": "旧考勤制度", "category": "考勤", "version": "1.0", "effective_date": "2026-08-01"},
            FileStorage(stream=BytesIO(old_text.encode()), filename="old-attendance.md", content_type="text/markdown"),
        )
        old_version = db.session.scalar(db.select(PolicyVersion).where(PolicyVersion.policy_id == policy.id))
        update_policy_version(old_version.id, {"status": "active"})

    result = app.test_cli_runner().invoke(args=["seed-policies"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        policy = db.session.scalar(db.select(Policy).where(Policy.code == "ATTEND-001"))
        versions = {item.version: item.status for item in policy.versions}
        assert versions == {"1.0": "inactive", "2.0": "active"}
        assert db.session.scalar(
            db.select(db.func.count(Clause.id)).join(PolicyVersion).where(PolicyVersion.status == "active")
        ) == 122


def test_representative_questions_recall_real_active_clauses(app):
    seeded = app.test_cli_runner().invoke(args=["seed-policies"])
    assert seeded.exit_code == 0, seeded.output
    indexed = app.test_cli_runner().invoke(args=["build-index"])
    assert indexed.exit_code == 0, indexed.output

    dataset_path = Path(__file__).resolve().parents[1] / "data" / "retrieval_evaluation.json"
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    required_topics = ("试用期", "年假", "补卡", "差旅报销", "加班", "调休", "离职")
    assert all(any(topic in item["question"] for item in cases) for topic in required_topics)
    hits = 0
    with app.app_context():
        for case in cases:
            results, _fingerprint = hybrid_search(case["question"], limit=3)
            hits += any(
                item["policy_code"] == case["policy_code"] and item["clause_number"] == case["clause_number"]
                for item in results
            )
            assert all(LIBRARY_NAME in item["text"] for item in results)
    assert hits / len(cases) >= 0.85, f"Recall@3={hits}/{len(cases)}"
