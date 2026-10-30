"""What a person reads in a memo or a pack is the text that was checked (hostile-model review, 2026-10-30).

Ingest holds the contract, its name, guidance and questions to that; nothing held the strings the model writes, and the
record keeps them as written. A direction override in a verified quote printed "fifteen (51) days" in the memo, under
"found in the document text", where the contract says fifteen (15): html.escape leaves format characters alone, and the
DOCX's xml_safe removed only control characters. Every string the memo and the pack's README show passes through one
display primitive (memo.visible), which names each invisible character in place and changes nothing in the record.
"""

from __future__ import annotations

import io
import json
import sys
import unicodedata
import zipfile

from fastapi.testclient import TestClient

from app.application.evidence_pack import README_TXT
from app.memo.visible import shown, shown_html
from app.providers.base import Generation
from tests.support import FakeProvider, upload_and_ask

QUESTION = "What notice is needed to terminate for convenience?"

# Overrides, embeddings, isolates, a zero-width space, a word joiner, a byte-order mark and a tag character.
HOSTILE = ["\u202e", "\u202c", "\u202b", "\u2067", "\u2069", "\u200b", "\u2060", "\ufeff", "\U000e0041"]


def hostile(text: str) -> str:
    return f"{text} {'x'.join(HOSTILE)} end"


class HostileProvider(FakeProvider):
    """The well-behaved answer, with every invisible character written into every string the model controls; the quote
    keeps the override around "(15)" that displayed as "(51)". A second proposal quotes nothing the contract has."""

    def generate_json(self, system: str, user: str, schema: dict[str, object]) -> Generation:
        payload = json.loads(super().generate_json(system, user, schema).text)
        finding = payload["findings"][0]
        for field in ("topic", "conclusion", "guidance_reference", "observed", "required", "suggested_position"):
            finding[field] = hostile(finding[field])
        finding["status_hint"] = "needs_review"  # so the memo prints the model's suggestion too
        quote = finding["evidence"][0]["quote"]
        finding["evidence"][0]["quote"] = quote.replace("(15)", "\u202e(15)\u202c")
        withheld = {**finding, "topic": hostile("Withheld topic"), "conclusion": hostile("Withheld sentence")}
        withheld["evidence"] = [{"section_id": finding["evidence"][0]["section_id"], "quote": "A sentence the contract does not have."}]
        payload["findings"].append(withheld)
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def hostile_run(client: TestClient) -> str:
    client.app.state.provider = HostileProvider()  # type: ignore[attr-defined]
    return str(upload_and_ask(client, QUESTION)["run_id"])


def memo_files(client: TestClient, run_id: str) -> tuple[str, str]:
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = client.get(memo["htmlUrl"]).text
    with zipfile.ZipFile(io.BytesIO(client.get(memo["docxUrl"]).content)) as package:
        body = package.read("word/document.xml").decode("utf-8")
    return html, body


def acting(text: str) -> list[str]:
    return [f"U+{ord(ch):04X}" for ch in HOSTILE if ch in text]


def test_the_memo_names_every_invisible_character_the_model_wrote(client: TestClient) -> None:
    html, body = memo_files(client, hostile_run(client))
    assert acting(html) == [], "the HTML memo lets them act"
    assert acting(body) == [], "the Word memo lets them act"
    # Each is named where the model wrote it, so the reader sees that something is there and what.
    for name in ("U+202E", "U+202C", "U+2067", "U+200B", "U+FEFF", "U+E0041"):
        assert name in html and f"[{name}]" in body, name
    for words in ("Termination for convenience", "Withheld topic", "Withheld sentence", "15 days", "at least 30 days", "thirty (30) days"):
        assert words in html and words in body, words


def test_the_packs_readme_says_where_the_model_wrote_them_and_shows_none_acting(client: TestClient) -> None:
    run_id = hostile_run(client)
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content)) as pack:
        readme = pack.read("README.txt").decode("utf-8")
        findings = json.loads(pack.read("findings.json"))
    assert acting(readme) == []
    assert readme.startswith(README_TXT), "the README's own text is unchanged"
    assert "finding 1, topic" in readme and "finding 1, span 1, quote" in readme and "[U+202E]" in readme
    # The record is the record: findings.json keeps every character the model wrote, for verify.py and for evidence.
    assert "\u202e" in findings[0]["topic"]


def test_control_an_honest_run_reads_as_before(client: TestClient) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    html, body = memo_files(client, run_id)
    assert "U+" not in html and "[U+" not in body
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content)) as pack:
        assert pack.read("README.txt").decode("utf-8") == README_TXT


def test_every_format_character_is_named_and_the_ones_text_needs_are_kept() -> None:
    kept = {"\u200c", "\u200d", "\u200e", "\u200f", "\u061c"}
    named = 0
    for code in (*range(0x20000), *range(0xE0000, 0xE1000)):
        ch = chr(code)
        if unicodedata.category(ch) != "Cf" or ch in kept:
            continue
        text = f"fifteen {ch}(15) days"
        assert ch not in shown(text) and f"[U+{code:04X}]" in shown(text), hex(code)
        assert ch not in shown_html(text) and f"U+{code:04X}" in shown_html(text), hex(code)
        named += 1
    assert named > 150, "the scan reached the format characters"
    # Kept as text, as the reader keeps them: joiners in a Persian word, an Arabic letter mark between Arabic digits.
    for text in ("\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u062f", "\u0661\u0665\u061c/\u0663", "a\u200eb", "\U0001f468\u200d\U0001f469"):
        assert shown(text) == text and shown_html(text) == text
    # A selector or joiner is kept where it shapes or varies a character, and named between two ASCII letters or digits.
    assert shown("\u2764\ufe0f and 9\ufe0f\u20e3") == "\u2764\ufe0f and 9\ufe0f\u20e3"
    assert shown("9\ufe0f0 days") == "9[U+FE0F]0 days"


def test_the_html_marker_is_markup_and_everything_else_is_escaped() -> None:
    marker = "<span class='invisible' title='An invisible character (U+202E) in the recorded text'>U+202E</span>"
    assert shown_html("<b>\u202e</b>") == f"&lt;b&gt;{marker}&lt;/b&gt;"
    assert shown_html("Smith & Sons 'quoted'") == "Smith &amp; Sons &#x27;quoted&#x27;"
    assert sys.maxunicode >= 0xE0041  # a tag character is one code point here, as the API counts
