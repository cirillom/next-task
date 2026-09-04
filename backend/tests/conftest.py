import os
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient

os.environ["NEXT_TASK_DATABASE_URL"] = "sqlite:///./data/test-next-task.sqlite3"
os.environ["NEXT_TASK_COOKIE_SECURE"] = "false"
os.environ["NEXT_TASK_CREDENTIAL_SECRET"] = "test-credential-secret-at-least-thirty-two-characters"

from app.auth.security import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def create_user() -> Callable[[str, str, str], User]:
    def factory(email: str, password: str = "correct horse", name: str = "Test User") -> User:
        with SessionLocal() as db:
            user = User(email=email, display_name=name, password_hash=hash_password(password))
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    return factory


@pytest.fixture
def logged_in_client(create_user: Callable[[str, str, str], User]) -> Callable[[str], TestClient]:
    def factory(email: str) -> TestClient:
        create_user(email)
        test_client = TestClient(app)
        response = test_client.post(
            "/api/auth/login", json={"email": email, "password": "correct horse"}
        )
        assert response.status_code == 200
        return test_client

    return factory
