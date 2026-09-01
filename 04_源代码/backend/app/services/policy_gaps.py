from __future__ import annotations

from collections import Counter
from datetime import timedelta, timezone
from threading import Event, Thread
from typing import Any

from flask import Flask, current_app

from ..extensions import db
from ..models import Clause, Feedback, Policy, PolicyGapIssue, PolicyGapScan, PolicyStatus, PolicyVersion, QueryLog, utcnow
from .deepseek import ModelGenerationError, generate_policy_gap_analysis
from .policy_issues import serialize_policy_issue, upsert_policy_issue


def _dataset() -> dict[str, Any]:
    policies = []
    active_versions = list(db.session.scalars(
        db.select(PolicyVersion).where(PolicyVersion.status == PolicyStatus.ACTIVE.value).order_by(PolicyVersion.id).limit(20)
    ))
    for version in active_versions:
        clauses = list(db.session.scalars(db.select(Clause).where(Clause.policy_version_id == version.id).order_by(Clause.id).limit(20)))
        policies.append({
            "ref": f"policy:{version.id}",
            "title": version.policy.title,
            "category": version.policy.category,
            "version": version.version,
            "effective_date": version.effective_date.isoformat(),
            "clauses": [item.text[:250] for item in clauses],
        })

    logs = list(db.session.scalars(db.select(QueryLog).order_by(QueryLog.created_at.desc()).limit(1000)))
    grouped = Counter((item.question, item.result_status) for item in logs)
    questions = [
        {"ref": f"query:{index}", "question": question, "status": status, "count": count}
        for index, ((question, status), count) in enumerate(grouped.most_common(80), start=1)
    ]
    feedback_rows = list(db.session.scalars(db.select(Feedback).order_by(Feedback.created_at.desc()).limit(200)))
    feedback = [
        {
            "ref": f"feedback:{item.id}",
            "type": item.feedback_type,
            "category": item.auto_category,
            "status": item.status,
            "content": item.content[:500],
        }
        for item in feedback_rows
    ]
    return {"policies": policies, "questions": questions, "feedback": feedback}


def _heuristic_issues(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in dataset["questions"]:
        if item["status"] not in {"refusal", "clarification"}:
            continue
        category = "unanswered" if item["status"] == "refusal" else "unclear_rule"
        issues.append({
            "category": category,
            "severity": "high" if item["count"] >= 3 else "medium",
            "title": f"{'高频未回答' if category == 'unanswered' else '条件口径不清'}：{item['question'][:70]}",
            "description": f"该问题在匿名问答记录中出现 {item['count']} 次，当前结果为{'拒答' if category == 'unanswered' else '需要补充条件'}。",
            "suggested_action": "补充覆盖该事项的适用范围、办理条件、责任人和时限，并用原问题做检索回归。",
            "occurrences": item["count"],
            "evidence_refs": [item["ref"]],
        })
    feedback_groups = Counter(
        (item["type"], item["content"]) for item in dataset["feedback"]
        if item["type"] in {"missing_policy", "outdated_policy", "unclear"}
    )
    mapping = {"missing_policy": "missing_policy", "outdated_policy": "outdated", "unclear": "unclear_rule"}
    for (kind, content), count in feedback_groups.most_common(20):
        ref = next(item["ref"] for item in dataset["feedback"] if item["type"] == kind and item["content"] == content)
        issues.append({
            "category": mapping[kind], "severity": "high" if count >= 3 else "medium",
            "title": f"员工反馈：{content[:80]}",
            "description": f"发现 {count} 条同类制度反馈，需要 HR 核验知识库覆盖情况。",
            "suggested_action": "核对现行制度原文与生效版本，补充或修订后重建索引并复测。",
            "occurrences": count, "evidence_refs": [ref],
        })
    for policy in dataset["policies"]:
        joined = "\n".join(policy["clauses"])
        missing = []
        if not any(word in joined for word in ("申请", "提交", "办理")):
            missing.append("办理入口/提交方式")
        if not any(word in joined for word in ("审批", "负责人", "HR", "人力资源")):
            missing.append("审批责任人")
        if missing:
            issues.append({
                "category": "unclear_rule", "severity": "low",
                "title": f"{policy['title']}缺少可执行要素",
                "description": "制度文本中未明确检出：" + "、".join(missing) + "。",
                "suggested_action": "由制度负责人确认是否需补充办理角色、入口、材料和时限。",
                "occurrences": 1, "evidence_refs": [policy["ref"]],
            })
    return issues[:20]


def _evidence_details(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = dataset["policies"] + dataset["questions"] + dataset["feedback"]
    return {item["ref"]: item for item in values}


def run_policy_gap_scan(trigger_type: str = "manual") -> PolicyGapScan:
    dataset = _dataset()
    scan = PolicyGapScan(trigger_type=trigger_type, status="running", query_count=sum(item["count"] for item in dataset["questions"]), policy_count=len(dataset["policies"]))
    db.session.add(scan)
    db.session.flush()
    issues = _heuristic_issues(dataset)
    summary = f"已扫描 {len(dataset['policies'])} 个启用制度和 {scan.query_count} 条问答记录，发现 {len(issues)} 项待核验线索。"
    model_name = None
    try:
        generated = generate_policy_gap_analysis(dataset)
        issues = [item.model_dump() for item in generated.issues]
        summary = generated.summary
        model_name = current_app.config["DEEPSEEK_MODEL"]
    except ModelGenerationError as exc:
        current_app.logger.warning(
            "policy_gap_ai_fallback stage=%s category=%s status_code=%s exception_type=%s",
            exc.stage,
            exc.category,
            exc.status_code,
            exc.exception_type,
        )
        summary += " 当前使用本地规则分析，配置 AI 后将自动切换为语义审计。"

    evidence_map = _evidence_details(dataset)
    created_count = 0
    existing_count = 0
    upgraded_count = 0
    merged_count = 0
    for item in issues:
        refs = item.pop("evidence_refs", [])
        evidence = [evidence_map[ref] for ref in refs if ref in evidence_map]
        origin_question = next((row.get("question") for row in evidence if isinstance(row, dict) and row.get("question")), None)
        sources = ["ai_scan"]
        if any(str(row.get("ref", "")).startswith("query:") for row in evidence if isinstance(row, dict)):
            sources.append("qa_insight")
        if any(str(row.get("ref", "")).startswith("feedback:") for row in evidence if isinstance(row, dict)):
            sources.append("employee_feedback")
        issue, created, upgraded = upsert_policy_issue(
            scan_id=scan.id, evidence=evidence, sources=sources, origin_question=origin_question, **item,
        )
        if created:
            created_count += 1
        else:
            existing_count += 1
            if len(issue.sources or []) > len(set(sources)):
                merged_count += 1
        if upgraded:
            upgraded_count += 1
    scan.status = "completed"
    scan.summary = f"{summary} 新增 {created_count} 项、已有 {existing_count} 项、风险升级 {upgraded_count} 项、来源合并 {merged_count} 项。"
    scan.model_name = model_name
    scan.completed_at = utcnow()
    db.session.commit()
    return scan


def serialize_scan(scan: PolicyGapScan) -> dict[str, Any]:
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return {
        "id": scan.id, "trigger_type": scan.trigger_type, "status": scan.status,
        "summary": scan.summary, "query_count": scan.query_count, "policy_count": scan.policy_count,
        "model_name": scan.model_name, "error_message": scan.error_message,
        "started_at": scan.started_at.isoformat(),
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "issues": [serialize_policy_issue(item) for item in sorted(
            scan.issues, key=lambda value: (severity_order.get(value.severity, 9), -value.occurrences)
        )],
    }


def latest_policy_gap_scan(*, run_if_due: bool = True) -> PolicyGapScan | None:
    latest = db.session.scalar(db.select(PolicyGapScan).order_by(PolicyGapScan.started_at.desc()).limit(1))
    interval = timedelta(hours=float(current_app.config["POLICY_GAP_SCAN_INTERVAL_HOURS"]))
    latest_started_at = latest.started_at if latest else None
    if latest_started_at is not None and latest_started_at.tzinfo is None:
        # SQLite does not preserve timezone information even for timezone-aware columns.
        latest_started_at = latest_started_at.replace(tzinfo=timezone.utc)
    if run_if_due and (latest is None or latest_started_at < utcnow() - interval):
        return run_policy_gap_scan("scheduled")
    return latest


def start_policy_gap_scheduler(app: Flask) -> None:
    if not app.config.get("POLICY_GAP_SCAN_ENABLED"):
        return
    stop_event = Event()

    def worker() -> None:
        while not stop_event.wait(max(30, int(app.config["POLICY_GAP_SCAN_POLL_SECONDS"]))):
            try:
                with app.app_context():
                    latest_policy_gap_scan(run_if_due=True)
            except Exception:
                app.logger.exception("scheduled policy gap scan failed")

    Thread(target=worker, name="policy-gap-scanner", daemon=True).start()
