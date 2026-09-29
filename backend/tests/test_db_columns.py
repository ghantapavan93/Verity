"""An existing SQLite file gains the columns newer models declare, without losing rows."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app import db as db_module


def test_ensure_columns_adds_missing_columns(tmp_path: Path) -> None:
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE documents (id VARCHAR(32) PRIMARY KEY, name VARCHAR(255), media_type VARCHAR(64), "
                "sha256 VARCHAR(64), pages INTEGER, created_at DATETIME)"
            )
        )
        connection.execute(text("INSERT INTO documents (id, name, media_type, sha256, pages) VALUES ('d1', 'old.docx', 'x', 'abc', 3)"))
    db_module.init_db(engine)
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text('PRAGMA table_info("documents")'))}
        assert "parse_ms" in columns
        assert connection.execute(text("SELECT name FROM documents WHERE id='d1'")).scalar() == "old.docx"
        run_columns = {row[1] for row in connection.execute(text('PRAGMA table_info("runs")'))}
        assert "reason" in run_columns and "fingerprint" in run_columns
        indexes = {row[1] for row in connection.execute(text('PRAGMA index_list("runs")'))}
        assert "ux_runs_fingerprint_active" in indexes


def test_fresh_databases_reject_unknown_stages_and_statuses(tmp_path: Path) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'new.db').as_posix()}")
    db_module.init_db(engine)
    columns = "id, document_id, question, stage, provider, model, prompt_version, prompt_hash, options_json, document_sha256, candidates_json, created_at"
    values = "'{id}', 'd1', 'q', '{stage}', 'fake', 'fake-1', 'v', 'h', '{{}}', 'abc', '[]', '2026-09-28 00:00:00'"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO documents (id, name, media_type, sha256, pages, created_at) VALUES ('d1', 'a.txt', 'text/plain', 'abc', 1, '2026-09-28 00:00:00')"
            )
        )
        connection.execute(text(f"INSERT INTO runs ({columns}) VALUES ({values.format(id='ok', stage='reading')})"))
    with pytest.raises(IntegrityError, match="ck_runs_stage"), engine.begin() as connection:
        connection.execute(text(f"INSERT INTO runs ({columns}) VALUES ({values.format(id='bad', stage='daydreaming')})"))
    with pytest.raises(IntegrityError, match="ck_findings_status"), engine.begin() as connection:
        connection.execute(
            text("INSERT INTO findings (id, run_id, ordinal, topic, status, status_source, conclusion) VALUES ('f1', 'ok', 0, 't', 'maybe', 'model_hint', 'c')")
        )


def test_api_schemas_carry_the_shared_vocabularies() -> None:
    """The stage, status and reason types on the wire are the very types the ORM and the CHECKs use."""
    from typing import get_args

    from pydantic import BaseModel

    from app import models, schemas

    def annotation(model: type[BaseModel], field: str) -> object:
        return model.model_fields[field].annotation

    assert annotation(schemas.RunOut, "stage") == models.RunStageName
    assert annotation(schemas.RunOut, "reason") == (models.RunReasonName | None)
    assert annotation(schemas.FindingOut, "status") == models.FindingStatusName
    assert annotation(schemas.StageOut, "stage") == models.RunStageName
    assert set(get_args(models.RunStageName)) == set(models.RUN_STAGES) >= set(models.TERMINAL_STAGES)
