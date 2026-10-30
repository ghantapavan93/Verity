"""A store written by any earlier build opens with the constraints a fresh store has, its rows and their joins intact.

Found on 2026-10-30 (stress test, store evolution 4): stores created by release-2026-10-02 and before never gained
ck_findings_status_source, because SQLite cannot add a CHECK in place and init_db only added columns. They accepted every
(status, source) pair a fresh store refuses. The wider class is any CHECK changed after a store exists: added, widened or
narrowed under the same name. A widened vocabulary is the harmful direction, since the old store then refuses the new
build's legitimate rows, in production only. The skeptic also showed the textbook rebuild losing every span and review
(DROP TABLE cascades with foreign keys on) or failing on RENAME (another table's trigger names the table).
"""

from __future__ import annotations

import sqlite3
from itertools import product
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app import db
from app.models import FINDING_STATUSES, STATUSES_BY_SOURCE

OLD_STORE = Path(__file__).parent / "fixtures" / "store-release-2026-10-02.sql"
COUNTED = ("runs", "findings", "evidence_spans", "finding_reviews", "documents", "sections", "run_stages")


def old_store(tmp_path: Path, *extra: str) -> tuple[Path, Engine]:
    """The release-2026-10-02 store, with `extra` statements applied beneath its triggers: how a row the triggers or the
    code would now refuse could stand in a store of that age."""
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(OLD_STORE.read_text(encoding="utf-8"))
        triggers = connection.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'").fetchall()
        for name, _sql in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        for statement in extra:
            connection.execute(statement)
        for _name, sql in triggers:
            connection.execute(sql)
    return path, db.make_engine(f"sqlite:///{path.as_posix()}")


def fresh_store(tmp_path: Path) -> Engine:
    fresh = db.make_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    db.init_db(fresh)
    return fresh


def counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in COUNTED}


def schema(path: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(path) as connection:
        return sorted(connection.execute("SELECT name, COALESCE(sql, '') FROM sqlite_master"))


def write(path: Path, statement: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(statement)


def test_the_fixture_is_the_store_the_finding_names(tmp_path: Path) -> None:
    """Control: the old store really lacks the constraint, and a fresh store really has it."""
    fresh = fresh_store(tmp_path)
    with fresh.connect() as connection:
        assert "ck_findings_status_source" in db.describe_store(connection)["findings"]["checks"]
    path, engine = old_store(tmp_path)
    with sqlite3.connect(path) as connection:
        assert set(db.describe_store(connection)["findings"]["checks"]) == {"ck_findings_status"}
    engine.dispose()


def test_an_old_store_opens_described_as_a_fresh_store_is(tmp_path: Path) -> None:
    path, engine = old_store(tmp_path)
    before = counts(path)
    db.init_db(engine)
    fresh = fresh_store(tmp_path)
    with engine.connect() as old, fresh.connect() as new:
        described, expected = db.describe_store(old), db.describe_store(new)
    assert described == expected  # columns, foreign keys, CHECKs, indexes and triggers alike; only column order differs
    assert counts(path) == before  # nothing lost: no cascade from the dropped table
    with sqlite3.connect(path) as connection:
        joined = connection.execute("SELECT COUNT(*) FROM evidence_spans s JOIN findings f ON f.id = s.finding_id").fetchone()[0]
        assert joined == before["evidence_spans"] and connection.execute("PRAGMA foreign_key_check").fetchall() == []
    engine.dispose()


ALLOWED: dict[str, tuple[str, ...]] = {source: tuple(statuses) for source, statuses in STATUSES_BY_SOURCE.items()}
NO_DECISION = [(status, source) for status, source in product(FINDING_STATUSES, [*ALLOWED, "invented"]) if status not in ALLOWED.get(source, ())]


@pytest.mark.parametrize(("status", "source"), NO_DECISION)
def test_after_opening_the_old_store_refuses_every_pair_no_decision_makes(tmp_path: Path, status: str, source: str) -> None:
    path, engine = old_store(tmp_path)
    db.init_db(engine)
    engine.dispose()
    with pytest.raises(sqlite3.IntegrityError, match="ck_findings_status_source"):
        write(path, f"INSERT INTO findings (id, run_id, ordinal, topic, status, status_source, conclusion) "
                    f"SELECT 'probe', id, 99, 't', '{status}', '{source}', 'c' FROM runs LIMIT 1")  # fmt: skip


def test_control_a_pair_a_decision_makes_is_taken(tmp_path: Path) -> None:
    path, engine = old_store(tmp_path, "UPDATE runs SET stage = 'reading'")  # an open run: its findings may still be written
    db.init_db(engine)
    engine.dispose()
    write(path, "INSERT INTO findings (id, run_id, ordinal, topic, status, status_source, conclusion) "
                "SELECT 'probe', id, 99, 't', 'pass', 'model_hint', 'c' FROM runs LIMIT 1")  # fmt: skip


def test_a_finished_run_stays_immutable_after_the_rebuild(tmp_path: Path) -> None:
    path, engine = old_store(tmp_path)
    db.init_db(engine)
    engine.dispose()
    for statement in ("UPDATE findings SET status = 'pass'", "DELETE FROM findings", "UPDATE evidence_spans SET quote = 'x'", "DELETE FROM runs"):
        with pytest.raises(sqlite3.IntegrityError, match="a finished run is immutable"):
            write(path, statement)


def test_a_vocabulary_changed_under_the_same_name_is_applied(tmp_path: Path) -> None:
    """The store's ck_findings_status names a narrower vocabulary than the models: what a widened one looks like to an
    old store. Comparing names only would miss it, and the new build's legitimate 'unresolved' would be refused."""
    path, engine = old_store(tmp_path, "UPDATE runs SET stage = 'reading'")
    with sqlite3.connect(path) as connection:
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'findings'").fetchone()[0]
        narrowed = ddl.replace("'missing', 'unresolved'", "'missing'")
        assert narrowed != ddl
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute("UPDATE sqlite_master SET sql = ? WHERE name = 'findings'", (narrowed,))
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="ck_findings_status"):
        connection.execute("UPDATE findings SET status = 'unresolved', status_source = 'no_evidence'")
    db.init_db(engine)
    engine.dispose()
    write(path, "UPDATE findings SET status = 'unresolved', status_source = 'no_evidence'")


def test_a_row_the_new_constraint_refuses_stops_the_opening_and_changes_nothing(tmp_path: Path) -> None:
    path, engine = old_store(tmp_path, "UPDATE runs SET stage = 'reading'", "UPDATE findings SET status = 'pass', status_source = 'no_evidence'")
    with sqlite3.connect(path) as connection:
        (finding_id,) = connection.execute("SELECT id FROM findings").fetchone()
    before_schema, before_counts = schema(path), counts(path)
    with pytest.raises(db.StoreDrift, match=rf"ck_findings_status_source.*{finding_id}"):
        db.init_db(engine)
    engine.dispose()
    assert counts(path) == before_counts
    assert [row for row in schema(path) if row[0] == "findings"] == [row for row in before_schema if row[0] == "findings"]
    assert {name for name, _ in schema(path) if name.startswith("trg_")} >= {name for name, _ in before_schema if name.startswith("trg_")}


def test_a_null_the_models_refuse_stops_the_opening_and_is_named(tmp_path: Path) -> None:
    """The fresh review (2026-10-30): only CHECKs were read before the rebuild, so a NULL in a NOT NULL column failed the
    copy with SQLite's message and no id."""
    path, engine = old_store(tmp_path, "UPDATE runs SET stage = 'reading'")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA writable_schema=ON")
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'findings'").fetchone()[0]
        connection.execute("UPDATE sqlite_master SET sql = ? WHERE name = 'findings'", (ddl.replace("conclusion TEXT NOT NULL", "conclusion TEXT"),))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE findings SET conclusion = NULL")
        (finding_id,) = connection.execute("SELECT id FROM findings").fetchone()
    before = counts(path)
    with pytest.raises(db.StoreDrift, match=rf"NOT NULL findings\.conclusion refuses findings {finding_id}"):
        db.init_db(engine)
    engine.dispose()
    assert counts(path) == before


def test_a_dangling_reference_the_rebuild_did_not_make_does_not_stop_it(tmp_path: Path) -> None:
    """A reference already dangling in another table is the store's, not the rebuild's: foreign_key_check is compared
    before and after, never read whole after (the fresh review, 2026-10-30)."""
    path, engine = old_store(
        tmp_path,
        "INSERT INTO finding_reviews (finding_id, verdict, reviewer, created_at) VALUES ('gone', 'confirmed', 'probe', '2026-10-30 00:00:00')",
    )
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall()  # control: it dangles before
    before = counts(path)
    db.init_db(engine)
    engine.dispose()
    assert counts(path) == before
    with sqlite3.connect(path) as connection:
        assert "ck_findings_status_source" in db.describe_store(connection)["findings"]["checks"]


def test_a_fresh_store_is_not_rebuilt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: nothing drifts, so nothing is rebuilt; the check is a read of sqlite_master."""
    engine = db.make_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    db.init_db(engine)
    rebuilt: list[str] = []
    monkeypatch.setattr(db, "_rebuild", lambda _engine, table, _declared: rebuilt.append(table))
    db.init_db(engine)
    assert rebuilt == []
    engine.dispose()
