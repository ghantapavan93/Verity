"""One reader of where a contract defines a term (stress test, 2026-10-30, second wave).

Three readers found definitions and disagreed: the links that hand a clause's definitions to the model (runs/links.py)
read every pair of quotation marks a contract is drafted with and up to three words before the defining verb; the
reading's section labels (ingest/sections.split_lead_in) read three kinds of quotes and the verb right after the term;
the family fingerprint (families/fingerprint.py) read double quotes only. So a UK definition in single quotes was linked
but neither labelled nor fingerprinted, '"Agreement" as amended means' was linked only, and '"including" means
"including without limitation"' was labelled "including", a word of construction the links refuse. The invariant: one
definition of a definition (ingest/terms.py), which each reader asks; what a reader then keeps (the fingerprint keeps
capitalised terms) is its own.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.families.fingerprint import defined_terms
from app.ingest.sections import split_lead_in
from app.ingest.terms import defined_at_start, definitions
from app.runs.links import _definitions


@dataclass
class _Section:
    number: str
    heading: str
    text: str


DEFINING = [
    ('"Agreement" means this agreement and its schedules.', "Agreement"),
    ("“Business Day” means a day banks open in London.", "Business Day"),
    ("‘Customer Data’ means the data the Customer provides.", "Customer Data"),
    ("'Initial Term' has the meaning given in clause 4.", "Initial Term"),
    ("«Fees» shall mean the fees in the Order Form.", "Fees"),
    ("„Services“ includes the support services.", "Services"),
    ('"Deliverables" as used herein means the work product.', "Deliverables"),
    ('"Effective Date" shall have the meaning set out above.', "Effective Date"),
    ('"Term" will have the meaning given in Schedule 1.', "Term"),
    ("‘Customer’s Affiliate’ means any company it controls.", "Customer’s Affiliate"),
]


@pytest.mark.parametrize(("sentence", "term"), DEFINING)
def test_every_reader_finds_the_same_defined_term(sentence: str, term: str) -> None:
    assert [found for found, _ in definitions(sentence)] == [term]
    assert defined_at_start(sentence) == term
    assert split_lead_in(sentence) == (term, sentence), "the reading labels the definition by its term"
    assert _definitions([_Section("1", "Definitions", sentence)]) == {term: 0}, "the links find it"
    assert defined_terms(sentence) == {term.lower()}, "the fingerprint finds it"


NOT_DEFINING = [
    '"including" means "including without limitation".',
    '"to" means "to but excluding".',
    '"$" means United States dollars.',
    "the Parties' and the Members' interest includes all rights.",
    "The Supplier's obligations mean little without notice.",
]


@pytest.mark.parametrize("sentence", NOT_DEFINING)
def test_no_reader_takes_a_word_of_construction_or_an_apostrophe_for_a_term(sentence: str) -> None:
    assert list(definitions(sentence)) == []
    assert defined_at_start(sentence) is None
    assert _definitions([_Section("1", "Definitions", sentence)]) == {}
    assert defined_terms(sentence) == set()


def test_the_fingerprint_keeps_only_capitalised_terms_of_its_own_choosing() -> None:
    sentence = '"control" means the power to direct. "Affiliate" means a company under common control.'
    assert [term for term, _ in definitions(sentence)] == ["control", "Affiliate"]
    assert defined_terms(sentence) == {"affiliate"}


def test_control_a_heading_that_is_no_definition_is_labelled_as_before() -> None:
    assert split_lead_in("Governing Law. This Agreement is governed by English law.") == ("Governing Law", "This Agreement is governed by English law.")
