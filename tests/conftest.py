import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="meow-"))
os.environ["DATA_DIR"] = str(_root)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["DAILY_TZ"] = "America/New_York"

import pytest


@pytest.fixture(autouse=True)
def fresh_database():
    import app.models  # noqa: F401
    from app.database import Base, engine

    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client(fresh_database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
