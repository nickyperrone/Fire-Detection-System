import os
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest
import yaml
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alembic import command
from app.boundaries import allowed_area
from app.db import get_session
from app.main import app
from app.models import Base
from app.routers.dependencies import http_client, mail_sender, require_owner
from app.services.territories import DEFAULT_OWNER

BACKEND = Path(__file__).resolve().parents[1]
ARGENTINA = allowed_area("data/boundaries/argentina.geojson", 1000)
FIXTURES = Path(__file__).parent / "fixtures"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://fieldwatch:fieldwatch@localhost:5433/fieldwatch_test",
)


@pytest.fixture(scope="session")
def thresholds() -> dict:
    return yaml.safe_load((BACKEND.parent / "config" / "thresholds.yaml").read_text())


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    try:
        engine.connect().close()
    except OperationalError:
        if os.environ.get("REQUIRE_TEST_DATABASE"):
            raise
        pytest.skip("PostGIS test database is not running (make db)")
    # Running the real migrations also tests them.
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    return engine


@pytest.fixture
def session(engine):
    with engine.begin() as connection:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def outbox() -> list[EmailMessage]:
    """Emails the API would have sent."""
    return []


@pytest.fixture
def anonymous(session, outbox):
    """The API with the test database and an outbox instead of SMTP, signed out."""
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[mail_sender] = lambda: outbox.append
    # No test reaches the internet: outside services answer "unavailable" unless a test says more.
    unavailable = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    app.dependency_overrides[http_client] = lambda: unavailable
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(anonymous):
    """The API signed in as the owner the command line uses."""
    app.dependency_overrides[require_owner] = lambda: DEFAULT_OWNER
    return anonymous


def pytest_collection_modifyitems(items):
    for item in items:
        if "session" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.db)
