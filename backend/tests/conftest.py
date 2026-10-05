import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db as db_module
from app.api import access
from app.main import create_app
from tests.support import FakeProvider


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.SessionLocal.configure(bind=engine)
    from app import config

    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    # The gate is off unless a test turns it on, whatever the environment of the machine running the tests holds.
    monkeypatch.setattr(config.settings, "access_secret", "")
    monkeypatch.setattr(config.settings, "access_required", False)
    # Every test is its own reader: the run-start limit (which applies with the gate off too, since 2026-10-02) starts
    # empty. Reset in place rather than monkeypatched, so a test's own monkeypatch.undo() cannot bring back a full one.
    access.run_starts.reset()
    access.exchanges.reset()
    provider = FakeProvider()
    app = create_app(provider=provider)
    with TestClient(app) as test_client:
        test_client.provider = provider
        yield test_client
