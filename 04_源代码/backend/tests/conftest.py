import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import EmployeeUser


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        db.session.add(
            EmployeeUser(
                username="test-staff",
                password_hash=generate_password_hash("88888888"),
                display_name="测试员工",
                department="测试部门",
            )
        )
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    test_client = app.test_client()
    with test_client.session_transaction() as user_session:
        user_session["employee_user_id"] = 1
    return test_client


@pytest.fixture()
def other_employee_client(app):
    with app.app_context():
        other = EmployeeUser(
            username="other-staff",
            password_hash=generate_password_hash("88888888"),
            display_name="其他员工",
            department="其他部门",
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    test_client = app.test_client()
    with test_client.session_transaction() as user_session:
        user_session["employee_user_id"] = other_id
    return test_client
