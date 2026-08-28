from __future__ import annotations

import json
from pathlib import Path

import click
from flask import Flask
from flask.cli import with_appcontext
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import AdminUser, Policy, PolicyVersion
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
