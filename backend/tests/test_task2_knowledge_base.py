from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfWriter
from werkzeug.security import generate_password_hash

from app.errors import ApiError, ErrorCode
from app.extensions import db
from app.models import AdminUser, IndexSnapshot, Policy, PolicyVersion
from app.services.chunking import split_clauses
from app.services.file_parser import TextBlock, parse_document


POLICY_TEXT = """# 测试制度
## 第一章 假期
第一条 员工年假为五天。
第二条 年假须提前三个工作日申请。
"""


def create_admin(app):
    with app.app_context():
        db.session.add(AdminUser(username="hr", password_hash=generate_password_hash("secret123")))
        db.session.commit()


def login(client):
    return client.post("/api/v1/admin/auth/login", json={"username": "hr", "password": "secret123"})


def upload(client, *, code="TEST-001", version="1.0"):
    return client.post(
        "/api/v1/admin/policies",
        data={
            "code": code,
            "title": "测试制度",
            "category": "测试",
            "version": version,
            "effective_date": "2026-08-01",
            "file": (BytesIO(POLICY_TEXT.encode()), f"policy-{version}.md"),
        },
        content_type="multipart/form-data",
    )


def test_parser_and_stable_chunking():
    blocks, mime = parse_document("policy.md", POLICY_TEXT.encode())
    first = split_clauses(blocks, "TEST-001", "1.0")
    second = split_clauses(blocks, "TEST-001", "1.0")
    assert mime == "text/markdown"
    assert [item.clause_number for item in first] == ["第一条", "第二条"]
    assert [item.stable_anchor for item in first] == [item.stable_anchor for item in second]


def test_docx_parser_and_scanned_pdf_rejection():
    document = Document()
    document.add_paragraph("第一条 DOCX 内容可以解析。")
    docx_stream = BytesIO()
    document.save(docx_stream)
    blocks, mime = parse_document("policy.docx", docx_stream.getvalue())
    assert blocks[0].text.startswith("第一条")
    assert mime.endswith("wordprocessingml.document")

    pdf_stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf_stream)
    with pytest.raises(ApiError) as error:
        parse_document("scan.pdf", pdf_stream.getvalue())
    assert error.value.code == ErrorCode.UNSUPPORTED_FILE


def test_admin_authentication_required_and_session(client, app):
    assert client.get("/api/v1/admin/policies").status_code == 401
    create_admin(app)
    response = login(client)
    assert response.status_code == 200
    assert response.get_json()["data"]["authenticated"] is True
    assert client.get("/api/v1/admin/auth/session").get_json()["data"]["admin"]["username"] == "hr"
    assert client.post("/api/v1/admin/auth/logout").status_code == 200


def test_upload_version_activation_reader_and_index(client, app):
    create_admin(app)
    login(client)
    response = upload(client)
    assert response.status_code == 201
    version_id = response.get_json()["data"]["versions"][0]["id"]
    assert response.get_json()["data"]["versions"][0]["clause_count"] == 2

    activated = client.patch(f"/api/v1/admin/policy-versions/{version_id}", json={"status": "active"})
    assert activated.status_code == 200
    reader = client.get(f"/api/v1/policies/{version_id}/reader").get_json()["data"]
    assert len(reader["clauses"]) == 2
    assert reader["clauses"][0]["stable_anchor"].startswith("test-001-1.0-")

    rebuilt = client.post("/api/v1/admin/index/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.get_json()["data"]["status"] == "ready"
    search = client.post("/api/v1/admin/search/test", json={"question": "年假需要提前多久申请？"})
    assert search.status_code == 200
    assert search.get_json()["data"]["results"][0]["clause_number"] == "第二条"
    with app.app_context():
        assert db.session.scalar(db.select(IndexSnapshot).where(IndexSnapshot.is_current.is_(True))) is not None


def test_single_active_version_and_index_becomes_stale(client, app):
    create_admin(app)
    login(client)
    first = upload(client, version="1.0").get_json()["data"]["versions"][0]["id"]
    client.patch(f"/api/v1/admin/policy-versions/{first}", json={"status": "active"})
    client.post("/api/v1/admin/index/rebuild")
    second_response = upload(client, version="2.0")
    second = next(item["id"] for item in second_response.get_json()["data"]["versions"] if item["version"] == "2.0")
    client.patch(f"/api/v1/admin/policy-versions/{second}", json={"status": "active"})
    status = client.get("/api/v1/admin/index/status").get_json()["data"]
    assert status["status"] == "stale"
    with app.app_context():
        versions = list(db.session.scalars(db.select(PolicyVersion).order_by(PolicyVersion.version)))
        assert [item.status for item in versions] == ["inactive", "active"]


def test_duplicate_and_active_delete_are_rejected(client, app):
    create_admin(app)
    login(client)
    response = upload(client)
    version_id = response.get_json()["data"]["versions"][0]["id"]
    assert upload(client).status_code == 409
    client.patch(f"/api/v1/admin/policy-versions/{version_id}", json={"status": "active"})
    assert client.delete(f"/api/v1/admin/policy-versions/{version_id}").status_code == 409


def test_unsupported_upload_is_rejected(client, app):
    create_admin(app)
    login(client)
    response = client.post(
        "/api/v1/admin/policies",
        data={
            "code": "BAD-001",
            "title": "错误文件",
            "category": "测试",
            "version": "1.0",
            "effective_date": "2026-08-01",
            "file": (BytesIO(b"binary"), "policy.exe"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 415


def test_file_body_limit_is_enforced(client, app):
    create_admin(app)
    login(client)
    app.config["UPLOAD_MAX_BYTES"] = 8
    response = client.post(
        "/api/v1/admin/policies",
        data={
            "code": "BIG-001",
            "title": "超大文件",
            "category": "测试",
            "version": "1.0",
            "effective_date": "2026-08-01",
            "file": (BytesIO("第一条 文件内容".encode()), "big.md"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 413


def test_delete_last_draft_removes_policy(client, app):
    create_admin(app)
    login(client)
    response = upload(client)
    version_id = response.get_json()["data"]["versions"][0]["id"]
    assert client.delete(f"/api/v1/admin/policy-versions/{version_id}").status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(Policy).where(Policy.code == "TEST-001")) is None
