from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import click
from flask import Flask
from flask.cli import with_appcontext
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from .extensions import db
from .demo_policy_catalog import LIBRARY_NAME, POLICY_CATALOG, catalog_clause_count, render_policy
from .models import (
    AdminUser,
    Answer,
    Conversation,
    EmployeeUser,
    Feedback,
    FeedbackEvent,
    FeedbackStatus,
    Message,
    MessageRole,
    Policy,
    PolicyVersion,
    QueryLog,
    utcnow,
)
from .services.indexing import rebuild_index
from .services.employee_context import build_employee_business_context
from .services.policies import create_policy_version, update_policy_version
from .services.retrieval import hybrid_search


DEMO_PASSWORD = "88888888"


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    @with_appcontext
    def init_db() -> None:
        """Create tables for local development and smoke testing."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.password_option(confirmation_prompt=True)
    @with_appcontext
    def create_admin(username: str, password: str) -> None:
        normalized = username.strip()
        if not normalized:
            raise click.ClickException("Username cannot be empty.")
        if len(password) < 8:
            raise click.ClickException("Password must contain at least 8 characters.")
        existing = db.session.scalar(db.select(AdminUser).where(AdminUser.username == normalized))
        if existing:
            raise click.ClickException("Admin username already exists.")
        user = AdminUser(username=normalized, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin '{normalized}' created.")

    @app.cli.command("seed-demo-data")
    @with_appcontext
    def seed_demo_data() -> None:
        """Create demo accounts and representative employee/HR activity data."""
        password_hash = generate_password_hash(DEMO_PASSWORD)
        admins = list(db.session.scalars(db.select(AdminUser)))
        if not admins:
            admins = [AdminUser(username="admin", password_hash=password_hash)]
            db.session.add_all(admins)
        for admin in admins:
            admin.password_hash = password_hash
            admin.is_active = True

        staff = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "staff"))
        if staff is None:
            staff = EmployeeUser(
                username="staff",
                password_hash=password_hash,
                display_name="陈晨 · 工号 E1001",
                department="产品与技术中心",
            )
            db.session.add(staff)
        else:
            staff.password_hash = password_hash
            staff.is_active = True
            staff.display_name = "陈晨 · 工号 E1001"
        staff.department = "产品与技术中心"
        staff.job_title = "产品经理"
        staff.hire_date = date(2023, 3, 1)
        staff.employee_status = "regular"
        staff.tenure_years = 3.5
        staff.direct_manager = "王强"
        staff.hrbp = "李娜"
        staff.annual_leave_entitlement = 5
        staff.annual_leave_balance = 3.5
        db.session.flush()

        staff_profile = build_employee_business_context(staff).profile_snapshot

        client_session_id = f"employee-{staff.id}"
        existing = db.session.scalar(
            db.select(Conversation).join(Answer).where(
                Conversation.client_session_id == client_session_id,
                Answer.knowledge_fingerprint == "demo-seed",
            )
        )
        legacy_conversations = list(
            db.session.scalars(
                db.select(Conversation).where(
                    Conversation.client_session_id == client_session_id,
                    Conversation.title.like("[演示]%"),
                )
            )
        )
        for conversation in legacy_conversations:
            conversation.title = (conversation.title or "").removeprefix("[演示]").strip()
        answer_contracts = {
            "年假如何计算？": {
                "status": "answer",
                "decision": "allowed",
                "summary": "符合",
                "missing_conditions": [],
                "next_steps": [{"text": "按 3.5 年累计工龄对应的年假档位核对可用余额。", "evidence_ids": []}],
                "clarification": {},
                "content": (
                    "明确结论：符合\n"
                    "原因：系统已从当前员工档案取得正式员工状态和 3.5 年累计工龄，无需再次填写。\n"
                    "下一步：按对应年假档位核对当前 3.5 天可用余额后申请。\n"
                    "制度依据：《休假管理制度》关于年假资格与累计工龄档位的规定。"
                ),
            },
            "差旅报销最晚什么时候提交？": {
                "status": "answer",
                "decision": "informational",
                "summary": "需要",
                "missing_conditions": [],
                "next_steps": [{"text": "差旅结束后 10 个工作日内提交报销单及合规票据。", "evidence_ids": []}],
                "clarification": {},
                "content": (
                    "明确结论：需要\n"
                    "原因：差旅结束后必须在制度规定期限内提交报销材料。\n"
                    "下一步：请在差旅结束后 10 个工作日内提交报销单及合规票据。\n"
                    "制度依据：《差旅报销制度》关于报销时限和票据要求的规定。"
                ),
            },
            "试用期可以申请年假吗？": {
                "status": "answer",
                "decision": "allowed",
                "summary": "可以",
                "missing_conditions": [],
                "next_steps": [{"text": "当前档案为正式员工，可直接按年假流程申请。", "evidence_ids": []}],
                "clarification": {},
                "content": (
                    "明确结论：可以\n"
                    "原因：系统优先使用当前登录档案；该员工为正式员工、累计工龄 3.5 年，符合年假资格。\n"
                    "下一步：核对当前 3.5 天年假余额后提交申请。\n"
                    "制度依据：《休假管理制度》关于年假资格与累计工龄的规定。"
                ),
            },
            "入职需要准备哪些材料？": {
                "status": "degraded",
                "decision": "informational",
                "summary": "需要",
                "missing_conditions": [],
                "next_steps": [{"text": "按入职通知准备身份、学历和公司要求的其他材料。", "evidence_ids": []}],
                "clarification": {},
                "content": (
                    "明确结论：需要\n"
                    "原因：办理入职必须提交身份、学历及公司通知列明的材料。\n"
                    "下一步：请按入职通知逐项准备，并在报到前向 HR 确认材料是否齐全。\n"
                    "制度依据：当前为本地降级提示，请以《入离职管理制度》原文和 HR 通知为准。"
                ),
            },
            "公司附近有哪些餐厅？": {
                "status": "refusal",
                "decision": "informational",
                "summary": "条件不足，暂时无法判断",
                "missing_conditions": [],
                "next_steps": [],
                "clarification": {},
                "content": (
                    "明确结论：条件不足，暂时无法判断\n"
                    "原因：该问题不属于公司 HR 制度范围，当前制度库没有可核验依据。\n"
                    "下一步：请改用地图或生活服务工具查询。\n"
                    "制度依据：无；系统不会用无关制度拼接答案。"
                ),
            },
        }
        if existing is None:
            now = utcnow()
            policies = list(db.session.scalars(db.select(Policy).order_by(Policy.id)))
            samples = [
                ("年假如何计算？", "正式员工累计工作满 1 年后可按制度享受年假，具体天数与累计工龄相关。", "answer", 180),
                ("差旅报销最晚什么时候提交？", "差旅结束后应在制度规定期限内提交报销单及票据。", "answer", 142),
                ("试用期可以申请年假吗？", "还需要确认累计工龄，补充条件后才能给出适用判断。", "clarification", 96),
                ("入职需要准备哪些材料？", "请准备身份、学历及公司要求的入职材料，并按通知完成报到。", "degraded", 210),
                ("公司附近有哪些餐厅？", "当前制度库没有足够依据回答该问题。", "refusal", 58),
            ]
            created_answers: list[Answer] = []
            for index, (question, summary, status, latency) in enumerate(samples):
                created_at = now - timedelta(days=8 - index * 2, hours=index)
                conversation = Conversation(
                    client_session_id=client_session_id,
                    title=question,
                    scenario_state={"employee_status": "regular"} if index != 2 else {"employee_status": "probation"},
                    created_at=created_at,
                    updated_at=created_at + timedelta(minutes=3),
                )
                db.session.add(conversation)
                db.session.flush()
                answer = Answer(
                    conversation_id=conversation.id,
                    question=question,
                    normalized_question=question,
                    status=status,
                    summary=summary,
                    scenario=conversation.scenario_state,
                    employee_profile_snapshot=staff_profile,
                    clarification={
                        "slot": "tenure_years",
                        "question": "你的累计工龄是多少？",
                        "options": [{"value": 0.5, "label": "不足 1 年"}, {"value": 2, "label": "1 年及以上"}],
                    }
                    if status == "clarification"
                    else {},
                    action_card={"applicable_conditions": [], "timeline": [], "materials": [], "cautions": []},
                    evidence_snapshot=[],
                    evidence_coverage=1.0 if status == "answer" else 0.0,
                    knowledge_fingerprint="demo-seed",
                    is_degraded=status == "degraded",
                    degraded_reason="演示：模型服务暂不可用" if status == "degraded" else None,
                    latency_ms=latency,
                    created_at=created_at + timedelta(minutes=2),
                )
                db.session.add(answer)
                db.session.flush()
                db.session.add_all(
                    [
                        Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=question, created_at=created_at),
                        Message(
                            conversation_id=conversation.id,
                            role=MessageRole.ASSISTANT.value,
                            content=summary,
                            created_at=created_at + timedelta(minutes=2),
                        ),
                    ]
                )
                db.session.add(
                    QueryLog(
                        conversation_id=conversation.id,
                        policy_id=policies[index % len(policies)].id if policies else None,
                        question=question,
                        result_status=status,
                        top_score=0.82 - index * 0.09,
                        hit_count=3 if status == "answer" else 0,
                        retrieval_latency_ms=max(latency // 3, 1),
                        total_latency_ms=latency,
                        is_degraded=status == "degraded",
                        created_at=created_at + timedelta(minutes=2),
                    )
                )
                created_answers.append(answer)

            feedback_samples = [
                (0, "suggestion", "希望年假回答能同时展示申请入口和所需材料。", FeedbackStatus.RESOLVED.value),
                (1, "unclear", "差旅报销期限的表达可以再明确一些。", FeedbackStatus.PROCESSING.value),
                (3, "missing_policy", "入职材料列表里缺少银行卡信息说明。", FeedbackStatus.OPEN.value),
                (4, "wrong_answer", "这不是制度问题，拒答提示很清楚。", FeedbackStatus.REJECTED.value),
            ]
            for offset, (answer_index, feedback_type, content, status) in enumerate(feedback_samples):
                answer = created_answers[answer_index]
                created_at = answer.created_at + timedelta(hours=2)
                feedback = Feedback(
                    client_session_id=client_session_id,
                    conversation_id=answer.conversation_id,
                    answer_id=answer.id,
                    primary_policy_id=policies[answer_index % len(policies)].id if policies else None,
                    submitter_name=staff.display_name if offset != 2 else None,
                    is_anonymous=offset == 2,
                    feedback_type=feedback_type,
                    content=content,
                    answer_snapshot={"question": answer.question, "summary": answer.summary, "scenario": answer.scenario, "evidence": []},
                    auto_category={"suggestion": "co_creation", "unclear": "usability", "missing_policy": "coverage", "wrong_answer": "accuracy"}[feedback_type],
                    status=status,
                    created_at=created_at,
                    updated_at=created_at + timedelta(hours=offset + 1),
                )
                db.session.add(feedback)
                db.session.flush()
                db.session.add(
                    FeedbackEvent(
                        feedback_id=feedback.id,
                        actor_type="employee",
                        action="submitted",
                        note="匿名提交" if feedback.is_anonymous else f"由 {staff.display_name} 提交",
                        created_at=created_at,
                    )
                )
                if status in {FeedbackStatus.PROCESSING.value, FeedbackStatus.RESOLVED.value}:
                    db.session.add(
                        FeedbackEvent(
                            feedback_id=feedback.id,
                            actor_type="admin",
                            action="start_processing",
                            note="HR 已受理，正在核对相关制度条款。",
                            event_data={"actor": admins[0].username, "from_status": "open", "to_status": "processing"},
                            created_at=created_at + timedelta(minutes=40),
                        )
                    )
                if status == FeedbackStatus.RESOLVED.value:
                    db.session.add(
                        FeedbackEvent(
                            feedback_id=feedback.id,
                            actor_type="admin",
                            action="resolve",
                            note="已补充办理材料说明并完成复核。",
                            event_data={"actor": admins[0].username, "from_status": "processing", "to_status": "resolved"},
                            created_at=created_at + timedelta(hours=2),
                        )
                    )
                if status == FeedbackStatus.REJECTED.value:
                    db.session.add(
                        FeedbackEvent(
                            feedback_id=feedback.id,
                            actor_type="admin",
                            action="reject",
                            note="该记录为正向评价，无需进入纠错流程。",
                            event_data={"actor": admins[0].username, "from_status": "open", "to_status": "rejected"},
                            created_at=created_at + timedelta(hours=1),
                        )
                    )

        # Keep previously seeded chat records aligned with the current answer contract.
        # This intentionally runs even when demo data already exists.
        for question, contract in answer_contracts.items():
            conversation = db.session.scalar(
                db.select(Conversation).join(Answer).where(
                    Conversation.client_session_id == client_session_id,
                    Conversation.title == question,
                    Answer.knowledge_fingerprint == "demo-seed",
                )
            )
            if conversation is None:
                continue
            answer = db.session.scalar(
                db.select(Answer)
                .where(
                    Answer.conversation_id == conversation.id,
                    Answer.question == question,
                    Answer.knowledge_fingerprint == "demo-seed",
                )
                .order_by(Answer.created_at.desc())
            )
            if answer is None:
                continue
            answer.status = contract["status"]
            answer.decision = contract["decision"]
            answer.summary = contract["summary"]
            answer.missing_conditions = contract["missing_conditions"]
            answer.next_steps = contract["next_steps"]
            answer.clarification = contract["clarification"]
            answer.employee_profile_snapshot = staff_profile
            answer.scenario = {
                **(answer.scenario or {}),
                **{field: value for field, value in staff_profile.items() if value is not None},
            }
            conversation.scenario_state = answer.scenario
            assistant_message = db.session.scalar(
                db.select(Message)
                .where(Message.conversation_id == conversation.id, Message.role == MessageRole.ASSISTANT.value)
                .order_by(Message.created_at.desc())
            )
            if assistant_message is not None:
                assistant_message.content = contract["content"]

        db.session.commit()
        click.echo("Demo accounts ready: staff / 88888888, admin / 88888888")
        click.echo("Employee query, feedback and HR processing records are ready.")

    @app.cli.command("seed-policies")
    @with_appcontext
    def seed_policies() -> None:
        """Load and activate the explicitly fictional training policy catalog."""
        sample_root = Path(app.root_path).parent / "sample_policies"
        sample_root.mkdir(parents=True, exist_ok=True)
        for spec in POLICY_CATALOG:
            code = spec["code"]
            version_name = spec["version"]
            rendered = render_policy(spec)
            source = sample_root / spec["filename"]
            source.write_text(rendered, encoding="utf-8")
            policy = db.session.scalar(db.select(Policy).where(Policy.code == code))
            version = None
            if policy:
                version = db.session.scalar(
                    db.select(PolicyVersion).where(
                        PolicyVersion.policy_id == policy.id,
                        PolicyVersion.version == version_name,
                    )
                )
            if version is None:
                policy = create_policy_version(
                    {
                        "code": code,
                        "title": spec["title"],
                        "category": spec["category"],
                        "version": version_name,
                        "effective_date": spec["effective_date"],
                    },
                    FileStorage(
                        stream=BytesIO(rendered.encode("utf-8")),
                        filename=spec["filename"],
                        content_type="text/markdown",
                    ),
                )
                version = db.session.scalar(
                    db.select(PolicyVersion).where(
                        PolicyVersion.policy_id == policy.id,
                        PolicyVersion.version == version_name,
                    )
                )
            assert version is not None
            if version.status != "active":
                update_policy_version(version.id, {"status": "active"})
            click.echo(f"Seeded {code} v{version_name} ({len(version.clauses)} clauses).")
        click.echo(f"{LIBRARY_NAME}: {len(POLICY_CATALOG)} policies, {catalog_clause_count()} active clauses expected.")

    @app.cli.command("build-index")
    @with_appcontext
    def build_index() -> None:
        """Atomically rebuild the hybrid retrieval index."""
        status = rebuild_index()
        click.echo(f"Index {status['status']}: {status['clause_count']} clauses, {status['fingerprint']}")

    @app.cli.command("evaluate-retrieval")
    @click.option("--dataset", type=click.Path(path_type=Path), default=None)
    @with_appcontext
    def evaluate_retrieval(dataset: Path | None) -> None:
        """Measure exact policy-clause Recall@3 on the retrieval evaluation set."""
        target = dataset or (Path(app.root_path).parent / "data" / "retrieval_evaluation.json")
        cases = json.loads(target.read_text(encoding="utf-8"))
        hits = 0
        misses: list[str] = []
        for case in cases:
            results, _ = hybrid_search(case["question"], limit=3)
            matched = any(
                result["policy_code"] == case["policy_code"] and result["clause_number"] == case["clause_number"]
                for result in results
            )
            hits += int(matched)
            if not matched:
                misses.append(case["question"])
        recall = hits / len(cases) if cases else 0.0
        click.echo(f"Recall@3: {recall:.2%} ({hits}/{len(cases)})")
        for question in misses:
            click.echo(f"MISS: {question}")
        if recall < 0.85:
            raise click.ClickException("Recall@3 is below the required 85% threshold.")
