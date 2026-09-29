"""Families are found from structure and judged against labels; every number is pairwise and exact."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import db as db_module
from app.families.fingerprint import Fingerprint, defined_terms, jaccard, normalise_heading, shingles, similarity
from app.families.service import Labels, LabelSet, cluster, evaluate, load_labels, pairwise, report
from app.ingest import PARSER_VERSION
from app.models import Document, Section


def make(name: str, headings: list[str], terms: list[str], text: str) -> Fingerprint:
    return Fingerprint(
        document_id=name,
        name=name,
        title=headings[0] if headings else name,
        sections=len(headings),
        chars=len(text),
        headings=frozenset(headings),
        terms=frozenset(terms),
        shingles=frozenset(shingles(text)),
    )


CORE = (
    "the supplier shall provide the deliverables in accordance with the specification and the buyer shall pay the charges within thirty days of a valid invoice"
)
SCHEDULE = (
    "the supplier shall provide the deliverables in accordance with the specification set out in this schedule "
    "and the charges are payable within thirty days of a valid invoice"
)
OTHER = "each party grants the other a limited licence to use its marks solely for the purpose of this partnership and only in the territory during the term"


def test_normalisation_strips_numbering_and_finds_defined_terms() -> None:
    assert normalise_heading("12.4 Termination for Convenience") == "termination for convenience"
    assert normalise_heading("Schedule 3 – Charges.") == "charges"
    defined = defined_terms('“Deliverables” means the goods and services. "Buyer" has the meaning given in the Order Form.')
    assert defined == {"deliverables", "buyer"}
    assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == 0.3333 and jaccard(frozenset(), frozenset()) == 0.0


def test_similar_structure_scores_high_and_unrelated_low() -> None:
    core = make("core.docx", ["definitions", "deliverables", "charges"], ["supplier", "buyer", "charges"], CORE)
    schedule = make("schedule.docx", ["definitions", "charges", "invoicing"], ["supplier", "charges"], SCHEDULE)
    other = make("other.docx", ["licence", "marks", "term"], ["marks", "territory"], OTHER)
    close = similarity(core, schedule)
    far = similarity(core, other)
    assert close.combined > 0.3 > far.combined
    assert close.shingles > far.shingles and close.terms > far.terms


def test_single_linkage_chains_pairs_and_evaluation_is_pairwise() -> None:
    a = make("a", ["x", "y"], ["p"], CORE)
    b = make("b", ["x", "y", "z"], ["p", "q"], SCHEDULE)
    c = make("c", ["m"], ["r"], OTHER)
    pairs = pairwise([a, b, c])
    assert cluster(["a", "b", "c"], pairs, 0.3) == [frozenset({"a", "b"}), frozenset({"c"})]
    assert cluster(["a", "b", "c"], pairs, 0.99) == [frozenset({"a"}), frozenset({"b"}), frozenset({"c"})]
    labels = LabelSet("t", "", (frozenset({"a", "b"}),))
    assert evaluate(["a", "b", "c"], pairs, 0.3, labels) == (1.0, 1.0, 1.0)
    assert evaluate(["a", "b", "c"], pairs, 0.99, labels) == (0.0, 0.0, 0.0)


def test_the_labels_name_only_documents_that_exist_in_the_corpus_list() -> None:
    labels = load_labels()
    assert len(labels.documents) == 20 and len(labels.sets) == 2
    assert all(len(prefix) == 16 for prefix in labels.documents.values())
    for label_set in labels.sets:
        for family in label_set.families:
            assert family <= set(labels.documents), f"{label_set.name}: {sorted(family)}"
    assert labels.sets[0].name == "suite" and len(labels.sets[0].families) == 5


def test_report_needs_two_labeled_documents_and_then_measures(tmp_path: Path) -> None:
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'f.db').as_posix()}")
    db_module.init_db(engine)
    with Session(engine) as session:
        assert not report(session).available
        for name, text in (("UK01.docx", CORE), ("UK02.docx", SCHEDULE), ("UK07.docx", OTHER)):
            document = Document(name=name, media_type="x", sha256=name, parser_version=PARSER_VERSION)
            document.sections = [
                Section(ordinal=0, number="1", heading="Definitions", text=text),
                Section(ordinal=1, number="2", heading=name, text=text[::-1]),
            ]
            session.add(document)
        session.commit()
        labels = Labels(note="", documents={"UK01.docx": "UK01.docx", "UK02.docx": "UK02.docx", "UK07.docx": "UK07.docx"}, sets=load_labels().sets)
        out = report(session, 0.15, labels)
    assert out.available and out.documents == 3 and out.missing == []
    assert any(set(f.members) == {"UK01.docx", "UK02.docx"} for f in out.families)
    suite = next(e for e in out.evaluations if e.label_set == "suite")
    assert suite.labeled_pairs == 1 and suite.precision == 1.0 and suite.recall == 1.0 and len(suite.sweep) == 19
