from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import click
from flask import Flask
from flask.cli import with_appcontext
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from .extensions import db
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
from .services.policies import create_policy_version, update_policy_version
from .services.retrieval import hybrid_search


SAMPLE_POLICIES = [
    ("ATTEND-001", "考勤管理制度", "考勤", "考勤管理制度.md"),
    ("LEAVE-001", "休假管理制度", "休假", "休假管理制度.md"),
    ("PAY-001", "薪酬福利制度", "薪酬福利", "薪酬福利制度.md"),
    ("TRAVEL-001", "差旅报销制度", "差旅", "差旅报销制度.md"),
    ("LIFECYCLE-001", "入离职管理制度", "员工关系", "入离职管理制度.md"),
]
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
                display_name="演示员工",
                department="产品与技术中心",
            )
            db.session.add(staff)
        else:
            staff.password_hash = password_hash
            staff.is_active = True
        db.session.flush()

        client_session_id = f"employee-{staff.id}"
        existing = db.session.scalar(
            db.select(Conversation).where(
                Conversation.client_session_id == client_session_id,
                Conversation.title.like("[演示]%"),
            )
        )
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
                    title=f"[演示] {question}",
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

        db.session.commit()
        click.echo("Demo accounts ready: staff / 88888888, admin / 88888888")
        click.echo("Employee query, feedback and HR processing records are ready.")

    @app.cli.command("seed-policies")
    @with_appcontext
    def seed_policies() -> None:
        """Load and activate the five fictional demonstration policies."""
        sample_root = Path(app.root_path).parent / "sample_policies"
        for code, title, category, filename in SAMPLE_POLICIES:
            policy = db.session.scalar(db.select(Policy).where(Policy.code == code))
            version = None
            if policy:
                version = db.session.scalar(
                    db.select(PolicyVersion).where(PolicyVersion.policy_id == policy.id, PolicyVersion.version == "1.0")
                )
            if version is None:
                source = sample_root / filename
                with source.open("rb") as stream:
                    policy = create_policy_version(
                        {
                            "code": code,
                            "title": title,
                            "category": category,
                            "version": "1.0",
                            "effective_date": "2026-08-01",
                        },
                        FileStorage(stream=stream, filename=filename, content_type="text/markdown"),
                    )
                version = db.session.scalar(
                    db.select(PolicyVersion).where(PolicyVersion.policy_id == policy.id, PolicyVersion.version == "1.0")
                )
            assert version is not None
            if version.status != "active":
                update_policy_version(version.id, {"status": "active"})
            click.echo(f"Seeded {code} v1.0 ({len(version.clauses)} clauses).")

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
