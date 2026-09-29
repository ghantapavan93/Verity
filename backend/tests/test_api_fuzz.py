"""Schemathesis over the API's own OpenAPI document: inputs nobody wrote by hand, against the app with
the fake provider. The false belief this catches: "every route validates what it is given". One route
did not until 2026-09-29 (a valid zip with a broken package came back as a 500); this keeps that class
of defect from returning. The event stream is left out: it holds the connection open by design.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app import db as db_module
from app.main import create_app
from tests.support import FakeProvider

_scratch = Path(tempfile.mkdtemp(prefix="workbench-fuzz-"))
_engine = db_module.make_engine(f"sqlite:///{(_scratch / 'fuzz.db').as_posix()}")
db_module.engine = _engine
db_module.SessionLocal.configure(bind=_engine)
config.settings.data_dir = _scratch

app = create_app(provider=FakeProvider())
schema = schemathesis.openapi.from_asgi("/openapi.json", app).exclude(path_regex=r"/events$")


@schema.parametrize()
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much])
def test_no_route_answers_with_a_server_error(case: schemathesis.Case[Any]) -> None:
    response = case.call()
    case.validate_response(response, checks=[not_a_server_error])  # type: ignore[list-item]
