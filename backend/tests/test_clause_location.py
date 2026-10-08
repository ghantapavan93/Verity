"""A verified passage is placed by the clause it sits in when the document's own text names one, never by a section label
that names another clause. Found by the QA campaign of 2026-10-08 on a real contract PDF: clauses written inline ("13.2
Governing Law. This Development Agreement shall be governed …") are body under the last standalone heading, so a
governing-law quote was cited as "§5 Intellectual Property (part 3)". The quote and its highlight were right; the place
was not. The label is read from the stored section text, so an old run shows what its own text says.
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingest.sections import PARAGRAPH_SEPARATOR, clause_label, clause_label_in, part_heading
from tests.support import GUIDANCE

SECTION = PARAGRAPH_SEPARATOR.join(
    [
        "5.1 Each party shall retain ownership of all intellectual property that it owned before the Effective Date.",
        "6. WRF Patents. A research foundation owns several patents relating to the expression of the enzyme.",
        "10. Term and Termination.",
        "10.1 This Agreement will begin on the Effective Date and continue for four (4) years.",
        "13. Miscellaneous.",
        "13.2 Governing Law. This Agreement shall be governed by the laws of the State of Minnesota.",
        "13.2.1 notwithstanding the foregoing, either party may seek injunctive relief in any court.",
        "13.3 the Parties agree that headings are for convenience only.",
    ]
)


def at(text: str, passage: str) -> str | None:
    return clause_label(text, text.index(passage))


def test_the_original_a_governing_law_passage_is_placed_by_its_own_clause() -> None:
    assert at(SECTION, "This Agreement shall be governed by") == "§13.2 Governing Law"
    assert at(SECTION, "A research foundation owns") == "§6 WRF Patents"
    assert at(SECTION, "continue for four (4) years") == "§10 Term and Termination"  # 10.1 is a sentence under clause 10


def test_siblings_a_sub_clause_keeps_its_clause_and_a_list_restarting_below_it_does_too() -> None:
    assert at(SECTION, "either party may seek injunctive relief") == "§13.2 Governing Law"
    listed = PARAGRAPH_SEPARATOR.join(
        [
            "4. Confidentiality. Each party keeps the other's information secret.",
            "1. the Receiving Party shall use it only for the work.",
            "2. it shall return it on request.",
        ]
    )
    assert at(listed, "it shall return it on request") == "§4 Confidentiality"


def test_controls_a_numbered_paragraph_outside_the_clause_ends_it_and_a_sentence_is_never_a_label() -> None:
    assert at(SECTION, "headings are for convenience only") is None  # 13.3 is not part of 13.2 and names no clause of its own
    assert at(SECTION, "Each party shall retain ownership") is None  # 5.1 is a numbered sentence, not a clause title
    assert clause_label("Fees are due within thirty (30) days of invoice.", 3) is None


def test_a_later_part_reads_on_from_the_parts_before_it_and_never_from_another_section() -> None:
    first, second = SECTION.split("13. Miscellaneous.")
    rows = [
        ("5", "Intellectual Property", "Each party keeps its own background rights."),
        ("5", part_heading("Intellectual Property", 1), first + "13. Miscellaneous."),
        ("5", part_heading("Intellectual Property", 2), second.lstrip()),
    ]
    # Parts 1 and 2 above are the same section split for size: part 2 opens inside clause 13.
    assert clause_label_in(rows, 2, rows[2][2].index("shall be governed")) == "§13.2 Governing Law"
    alone = [("7", part_heading("Warranties", 2), "No warranty is given except as stated in this section.")]
    assert clause_label_in(alone, 0, 0) is None  # no part 1 before it: nothing is borrowed from anywhere else
    other = [("6", part_heading("Patents", 1), "6. WRF Patents. The foundation owns them."), ("7", part_heading("Warranties", 2), "Text.")]
    assert clause_label_in(other, 1, 0) is None  # a part of another section is not read


def test_control_a_titled_list_at_the_start_of_a_section_is_not_a_clause_of_the_document() -> None:
    """The section's own number seeds the scan: a list numbered below it is a list inside the section (triage probe)."""
    rows = [
        (
            "8",
            "Indemnification",
            PARAGRAPH_SEPARATOR.join(
                [
                    "Each party shall indemnify the other as follows.",
                    "1. Indemnification by Licensee. Licensee shall defend Licensor.",
                    "2. Procedure. The indemnified party gives prompt notice.",
                ]
            ),
        )
    ]
    assert clause_label_in(rows, 0, rows[0][2].index("The indemnified party")) is None


def test_known_gap_a_titled_list_inside_a_clause_is_read_as_the_next_clause() -> None:
    """Recorded, not fixed (2026-10-08): a list inside clause 4 whose items carry titles and run past 4 ("5. Remedies.")
    is read as the document's clause 5. The number is printed where the label says; what it numbers is the list's."""
    listed = PARAGRAPH_SEPARATOR.join(
        [
            "4. Confidentiality. Each party keeps the other's information secret.",
            "1. Definitions. Information means business data.",
            "5. Remedies. Breach entitles the owner to relief.",
        ]
    )
    assert at(listed, "Breach entitles") == "§5 Remedies"


def test_a_clause_that_opens_inside_a_paragraph_places_the_passage_after_it() -> None:
    """Real-model smoke on a printed PDF, 2026-10-08: two clauses in one paragraph, and the governing-law quote was
    labelled by the first ("§3.1 Notices")."""
    printed = "3.1 Notices. Notices must be in writing. 3.2 Governing Law. This Agreement is governed by the laws of Delaware."
    assert clause_label(printed, printed.index("This Agreement is governed"), 3) == "§3.2 Governing Law"
    assert clause_label(printed, printed.index("Notices must be"), 3) == "§3.1 Notices"
    first = "3. General. These terms apply. 3.1 Notices. Notices must be in writing."
    assert at(first, "Notices must be") == "§3.1 Notices"  # a clause's first sub-clause continues it
    later = "15.5 Severability. A void term is severed. 15.10 Export Control. Neither party exports controlled goods."
    assert at(later, "Neither party exports") is None  # 15.10 is not the clause after 15.5: unknown, not either name


def test_controls_inside_a_paragraph_an_abbreviation_or_a_contents_line_names_no_clause() -> None:
    # Under clause 2, "No. 3 Joinder Agreement, Amendment No." reads like clause 3 opening; a period after "No" is not a
    # sentence end, so it is not adopted, and the clause it sits in is left unknown rather than named wrongly.
    joinder = "2. Joinder. The parties executed Amendment No. 3 Joinder Agreement, Amendment No. 4 thereto. The Borrower shall pay."
    assert at(joinder, "The Borrower shall pay") is None
    initialism = "2. Scope. This covers the U.S. 3 Regions. The supplier delivers."
    assert at(initialism, "The supplier delivers") is None
    contents = "1. Definitions. Terms used below. 12 Article 11 Audits. . . . . . 13 Article 12 Limited Warranties. . . . 14"
    assert at(contents, "Limited Warranties") is None  # a candidate that does not follow: the clause is no longer known
    unknown = "Fees are due monthly. 3.2 Governing Law. This Agreement is governed by the laws of Delaware."
    assert at(unknown, "This Agreement is governed") is None  # nothing found before: nothing inside a paragraph names one


def test_the_next_number_without_a_title_ends_the_clause_inside_a_paragraph() -> None:
    untitled = "3.1 Notices. Notices must be in writing. 3.2 The parties agree that Delaware law governs. It applies."
    assert clause_label(untitled, untitled.index("It applies"), 3) is None  # not 3.1, whatever 3.2 is called
    sub = "3.2 Governing Law. Delaware law governs. 3.2.1 the courts of Delaware hear disputes."
    assert clause_label(sub, sub.index("the courts of Delaware"), 3) == "§3.2 Governing Law"  # its own sub-clause


def test_known_gap_a_titled_figure_that_follows_reads_as_the_next_clause() -> None:
    """Recorded, not fixed (triage review, 2026-10-08): a sentence that starts with the next number and reads as a title
    ("4 Business Days.") is taken for clause 4. It needs both the number that follows and a capitalised title."""
    figure = "3.1 Notices. Notices arrive within ten days. 4 Business Days. Then the term ends."
    assert clause_label(figure, figure.index("Then the term ends"), 3) == "§4 Business Days"


PARAGRAPH = st.one_of(
    st.builds(
        lambda n, t: f"{n}. {t}. The parties agree to the terms below.",
        st.integers(1, 30),
        st.sampled_from(["Payment", "Governing Law", "Term and Termination", "Notices"]),
    ),
    st.builds(lambda n, m: f"{n}.{m} the supplier shall deliver the goods.", st.integers(1, 30), st.integers(1, 9)),
    st.sampled_from(["Fees are due monthly.", "1. the first item of a list.", "Section 9 applies.", "See Amendment No. 3 Joinder, Exhibit A."]),
    # two clauses in one paragraph, as a printed PDF often reads
    st.builds(
        lambda n, m, t: f"{n}.{m} Notices. Notices are in writing. {n}.{m + 1} {t}. The parties agree.",
        st.integers(1, 30),
        st.integers(1, 8),
        st.sampled_from(["Payment", "Governing Law", "Assignment"]),
    ),
)


@settings(max_examples=200, deadline=None)
@given(st.lists(PARAGRAPH, min_size=1, max_size=12), st.data())
def test_every_label_names_a_clause_printed_before_the_passage(paragraphs: list[str], data: st.DataObject) -> None:
    text = PARAGRAPH_SEPARATOR.join(paragraphs)
    start = data.draw(st.integers(0, len(text) - 1))
    label = clause_label(text, start)
    if label is None:
        return
    number, title = re.match(r"§(\S+) (.+)", label).groups()  # type: ignore[union-attr]
    # Printed as an opening at or before the passage: at the start of a paragraph, or after a sentence inside one.
    opening = re.compile(rf"(?:^|(?<=\n)|(?<=[.;:])\s+){re.escape(number)}\.? {re.escape(title)}[.:]", re.MULTILINE)
    assert any(m.start() <= start for m in opening.finditer(text)), label


INLINE = """SERVICES AGREEMENT

1. Term

This Agreement commences on the Effective Date and continues for twelve (12) months.

2. Termination for Convenience

2.1 Notice Period. Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider.

3. Governing Law

This Agreement is governed by the laws of the State of Delaware.
"""


def test_the_api_the_memo_and_the_evidence_pack_place_the_passage_by_its_clause(client: TestClient) -> None:
    document = client.post("/api/documents", files={"file": ("inline.txt", INLINE.encode("utf-8"), "text/plain")}).json()
    guidance = client.post("/api/guidance", json={"text": GUIDANCE}).json()
    run_id = client.post(
        "/api/runs", json={"documentId": document["id"], "guidanceId": guidance["id"], "question": "Can the customer terminate for convenience?"}
    ).json()["id"]
    run = client.get(f"/api/runs/{run_id}").json()
    span = run["findings"][0]["spans"][0]
    assert span["verified"] and span["clauseLabel"] == "§2.1 Notice Period"
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = client.get(f"/api/memos/{memo['id']}/html").text
    assert "§2.1 Notice Period · within §2 Termination for Convenience" in html
    pack = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content))
    assert json.loads(pack.read("findings.json"))[0]["spans"][0]["clause_label"] == "§2.1 Notice Period"


def test_control_a_passage_under_its_own_heading_has_no_clause_label(client: TestClient) -> None:
    from tests.support import upload_and_ask

    span = upload_and_ask(client, "Can the customer terminate for convenience?")["run"]["findings"][0]["spans"][0]
    assert span["verified"] and span["clauseLabel"] is None
