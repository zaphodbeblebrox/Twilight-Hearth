import os

os.environ.update(
    TH_ENV="test",
    TH_PUBLIC_URL="http://testserver",
    TH_SECRET_KEY="test-secret-test-secret-test-secret!",
    TH_GOOGLE_CLIENT_ID="test-client",
    TH_GOOGLE_CLIENT_SECRET="test-secret",
)
os.environ.pop("TH_DATABASE_URL", None)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import db as app_db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.security import create_invite  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database(tmp_path_factory):
    get_settings().media_dir = tmp_path_factory.mktemp("media")
    # Always a throwaway database, so the truncation below can never reach real data.
    get_settings().database_url = app_db.start_dev_database(tmp_path_factory.mktemp("pg"))
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean(database):
    yield
    tables = ", ".join(t.name for t in app_db.Base.metadata.sorted_tables)
    with app_db.get_engine().begin() as connection:
        connection.execute(text(f"truncate {tables} cascade"))


@pytest.fixture
def db():
    with Session(app_db.get_engine(), expire_on_commit=False) as session:
        yield session


def new_client() -> TestClient:
    return TestClient(app, headers={"origin": "http://testserver"})


def dev_login(client, name, token=None):
    if token:
        client.post("/api/auth/invite", json={"token": token})
    return client.post(
        "/api/auth/dev-login", json={"email": f"{name}@example.com", "name": name.title()}
    )


@pytest.fixture
def join(db):
    def make(name: str, admin: bool = False) -> TestClient:
        _, url = create_invite(db, admin=admin)
        client = new_client()
        assert dev_login(client, name, url.split("#")[1]).status_code == 204
        return client

    return make


def content(title="Pancakes", **extra):
    return {
        "title": title,
        "ingredient_groups": [{"id": "g1", "items": [{"id": "i1", "text": "1 1/2 cups flour"}]}],
        "steps": [{"id": "s1", "text": "Mix."}],
        **extra,
    }


def make_recipe(client, title="Pancakes", visibility="members", **extra):
    response = client.post(
        "/api/recipes", json={"content": content(title, **extra), "visibility": visibility}
    )
    assert response.status_code == 201, response.text
    return response.json()
