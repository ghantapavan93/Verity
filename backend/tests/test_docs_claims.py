"""The README states numbers and versions that the code decides, and each is read here from where the code keeps it.

A count or a version written into prose goes stale silently: the README said "seventeen parts" when the reader had
eighteen, its verifier row stopped at v6 when the code ran v7, it counted thirty or thirty-one browser flows when the
specs held thirty-five, and it described a code-confirmed pass eleven days after policy-v3 stopped writing one (war
room F-09, F-10, 2026-10-13).
The invariant: every number or version the README states as current equals what the code holds now. So a version
bumped, a part added, a flow, a hand mutant or a planted fault added fails here until the README says so too; the
backend suite and the interface's unit tests are not counted in the README at all, because their counts move with
every change and each gate run's log keeps them.

Two claims about ownership and process are held the same way: "confirmed by code" appears only in a sentence that marks
it as a policy-v2 record (since policy-v3 every pass is the model's, runs/status.py), and the README's list of what the
release gate does not run agrees with scripts/release-gate.sh.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.ingest import PARSER_VERSION
from app.ingest.coverage import PARTS
from app.retrieval.lexical import RETRIEVAL_VERSION
from app.runs.status import POLICY_VERSION
from app.verify.spans import VERIFIER_VERSION

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
README = ROOT / "README.md"

# Counts the README writes in words, zero to fifty-nine: "eighteen parts", "twenty-four hand mutants".
_ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_UNITS = (*_ONES, *_TEENS)
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
NUMBER_WORDS: dict[str, int] = {word: value for value, word in enumerate(_UNITS)} | _TENS
NUMBER_WORDS |= {f"{tens}-{_UNITS[unit]}": value + unit for tens, value in _TENS.items() for unit in range(1, 10)}

# The words that mark a "confirmed by code" sentence as being about the records policy-v2 made.
LEGACY = re.compile(r"policy-v2|before policy-v3|pre-v3")


def readme() -> str:
    return README.read_text(encoding="utf-8")


def as_number(token: str) -> int | None:
    """A count as the README writes it, "36" or "thirty-six"; None for a word that is not a number ("the")."""
    token = token.lower().replace(",", "")
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def stated_counts(text: str, noun: str, lead: str = "") -> list[int]:
    """Every count the text states for ``noun`` ("24 hand mutants"), after ``lead`` when one is given ("each of ")."""
    found = (as_number(m.group(1)) for m in re.finditer(rf"{lead}\b([a-z0-9,-]+) {noun}\b", text, re.IGNORECASE))
    return [n for n in found if n is not None]


def readme_lines(*prefixes: str) -> list[str]:
    """The README lines that hold a current claim: a release-checklist row or a command line, found by how it starts."""
    lines = [line for line in readme().splitlines() if line.lstrip().startswith(prefixes)]
    assert lines, f"the README no longer has a line starting with any of {prefixes}; move the claim and this test together"
    return lines


def playwright_flows() -> int:
    """Browser flows, counted from the specs the way scripts/data_audit.py counts them: one `test(` call each."""
    specs = sorted((ROOT / "e2e").glob("*.spec.ts"))
    assert specs, "no e2e/*.spec.ts beside the backend"
    return sum(len(re.findall(r"^\s*test\(", spec.read_text(encoding="utf-8"), re.MULTILINE)) for spec in specs)


def tuple_length(script: Path, name: str) -> int:
    """How many entries a module-level tuple literal holds, read from the syntax so the script is never run."""
    for node in ast.parse(script.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.AnnAssign | ast.Assign) and isinstance(node.value, ast.Tuple):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return len(node.value.elts)
    raise AssertionError(f"{script.name} has no tuple named {name}")


@pytest.mark.parametrize(
    ("label", "current"),
    [("policy", POLICY_VERSION), ("verifier", VERIFIER_VERSION), ("retrieval", RETRIEVAL_VERSION), ("reader", PARSER_VERSION)],
)
def test_every_version_the_readme_names_as_current_is_the_codes(label: str, current: str) -> None:
    # The README writes a version in force as `policy `policy-v6``; historical versions are written without backticks.
    named = re.findall(rf"\b{label} `([^`]+)`", readme())
    assert named, f"the README no longer names the {label} version in force as {label} `…`"
    assert set(named) == {current}, f"the README names {label} {sorted(set(named))}; the code runs {current}"


def test_the_parts_a_reading_accounts_for_are_counted_as_the_reader_has_them() -> None:
    # "each of eighteen parts": the README's other parts ("three parts that share one rule") are not the reader's.
    stated = stated_counts(readme(), "parts", lead="each of ")
    assert stated, "the README no longer says how many parts a reading accounts for"
    assert set(stated) == {len(PARTS)}, f"the README says {stated}; ingest/coverage.py PARTS has {len(PARTS)}"


def test_the_browser_flows_the_readme_counts_are_the_specs() -> None:
    flows = playwright_flows()
    for line in readme_lines("| What the tests cover |", "| Browser flows |", "| Checks |", "npm run e2e"):
        stated = stated_counts(line, "(?:Playwright|browser) flows")
        assert stated, f"this line no longer states the flows: {line[:120]}…"
        assert set(stated) == {flows}, f"the README says {stated} browser flows; e2e/*.spec.ts holds {flows}: {line[:120]}…"


def test_the_hand_mutants_and_planted_faults_are_the_scripts() -> None:
    mutants = tuple_length(BACKEND / "scripts" / "mutate_by_hand.py", "MUTANTS")
    faults = tuple_length(BACKEND / "scripts" / "trust_faults.py", "FAULTS")
    text = readme()
    assert set(stated_counts(text, "hand mutants")) == {mutants}, f"scripts/mutate_by_hand.py holds {mutants} mutants"
    assert set(stated_counts(text, "planted (?:trust )?faults")) == {faults}, f"scripts/trust_faults.py holds {faults} faults"


def sentences(text: str) -> Iterator[str]:
    """Sentences and clauses: split at a full stop, semicolon or question mark before a space, at a table cell, at a
    blank line. A legacy marker must sit in the same clause as the claim it qualifies."""
    for part in re.split(r"(?<=[.;?!])\s+|\s*\|\s*|\n\s*\n", text):
        if part.strip():
            yield " ".join(part.split())


def documents() -> list[Path]:
    return [README, *sorted((ROOT / "docs").glob("*.md")), ROOT / "proof" / "index.html"]


def test_confirmed_by_code_appears_only_as_a_policy_v2_record() -> None:
    """Since policy-v3 (2026-10-02) code confirms no pass: a pass is recorded as `model_hint` with code's sentence
    (runs/status.py, tests/test_pass_gate.py). The words survive only for the records policy-v2 made."""
    loose = [
        f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {sentence[:160]}"
        for path in documents()
        if path.exists()
        for sentence in sentences(path.read_text(encoding="utf-8"))
        if "confirmed by code" in sentence.lower() and not LEGACY.search(sentence)
    ]
    assert not loose, "a sentence presents a pass as confirmed by code without marking it a policy-v2 record:\n" + "\n".join(loose)


def test_the_marker_finds_a_present_tense_claim_and_passes_a_legacy_one() -> None:
    """Control: the check above would fail on the sentence the README carried until 2026-10-13, and passes its repair."""
    old = 'such a pass is recorded as `confirmed_days` and reads "Within guidance (confirmed by code)" under the heading "Code confirmed"'
    new = 'records made under policy-v2 carry `confirmed_days` and read "Within guidance (confirmed by code)"; nothing writes that source now'
    assert not any(LEGACY.search(s) for s in sentences(old) if "confirmed by code" in s)
    assert all(LEGACY.search(s) for s in sentences(new) if "confirmed by code" in s)


@pytest.mark.parametrize(("step", "in_gate"), [("mutate_by_hand", "mutate_by_hand"), ("format:check", "format:check")])
def test_what_the_readme_says_the_gate_does_not_run_it_does_not_run(step: str, in_gate: str) -> None:
    gate = (ROOT / "scripts" / "release-gate.sh").read_text(encoding="utf-8")
    not_run = [s for s in sentences(readme()) if s.startswith("It does not run")]
    assert len(not_run) == 1, "the README's sentence on what the release gate does not run moved; move this test with it"
    assert (step in not_run[0]) != (in_gate in gate), (
        f"scripts/release-gate.sh {'runs' if in_gate in gate else 'does not run'} {step}, and the README says otherwise"
    )


def _env_example() -> dict[str, str]:
    lines = (ROOT / "deploy" / "cloud" / "env.example").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.lstrip().startswith("#"))


def _config_default(variable: str) -> str:
    """The default config.py gives a setting when its variable is not set: `os.environ.get("<variable>", "<default>")`."""
    found = re.search(rf'os\.environ\.get\("{variable}", "([^"]*)"\)', (BACKEND / "app" / "config.py").read_text(encoding="utf-8"))
    assert found, variable
    return found.group(1)


def test_what_the_hosted_page_says_reaches_the_model_is_what_the_deployment_sends() -> None:
    """The hosted page said the model is sent "only the sections a question needs"; every question also carries the
    file's name and the guidance, and the opening sections when retrieval ranks none (counter-review, 2026-10-13). The
    page now lists all of it with numbers; each is read here from where the deployment decides it."""
    from app.analysis.service import SectionForPrompt, build_user_message

    story = (ROOT / "src" / "components" / "workbench" / "landing" / "LandingStory.tsx").read_text(encoding="utf-8")
    env = _env_example()
    k = int(env.get("WORKBENCH_RETRIEVAL_K") or _config_default("WORKBENCH_RETRIEVAL_K"))
    window = int(env.get("WORKBENCH_SECTION_WINDOW") or _config_default("WORKBENCH_SECTION_WINDOW"))
    words = {value: word for word, value in NUMBER_WORDS.items()}
    assert f"at most {words[k]} and each cut at {window:,} characters" in story
    assert f"the opening {words[k]} go instead" in story
    # Lexical retrieval reads the sections where they are stored; hybrid would send every section to an embedding model.
    assert (env.get("WORKBENCH_RETRIEVAL") or _config_default("WORKBENCH_RETRIEVAL")) == "bm25"
    # And the message carries what the page lists: the question, the guidance and the file's name, with the sections.
    section = SectionForPrompt(label="S1", number="1", heading="Term", text="This agreement lasts one year.")
    message = build_user_message("How long is the term?", "Prefer a short term.", "acme-msa.pdf", [section])
    assert all(part in message for part in ("How long is the term?", "Prefer a short term.", "acme-msa.pdf", "This agreement lasts one year."))
    assert "the question, any guidance, the contract's file name and the sections retrieval ranked" in story


def test_every_sentence_that_says_what_the_model_is_sent_names_the_file_too() -> None:
    """Three sentences on the hosted pages listed what reaches the model and left out the file's name, which every
    question carries (analysis/service.py build_user_message): two were corrected and the footer's was missed, and an
    operator's document and /break's lead said the same (counter-review, rounds 2 and 3, 2026-10-13). Every line of the
    interface or of a document that says the guidance is sent must name the file as well."""
    sources = [
        *(path for path in (ROOT / "src").rglob("*.tsx") if ".test." not in path.name),
        README,
        *(ROOT / "deploy").rglob("*.md"),
        *(ROOT / "docs").glob("*.md"),
        *(BACKEND / "app").rglob("*.py"),  # the API's own messages: the context-window refusal listed what fills it (round 4)
    ]
    # "Sent", or "handed to the model": "a conflict sends the finding to review" is not about the model.
    sent = re.compile(r"\bsent\b|handed to the model", re.IGNORECASE)
    missing = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in sources
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        # A list of what a question sends names the question and the guidance; "a run stores … the sections handed to
        # the model" is a list of what is kept, and names neither.
        if sent.search(line) and "question" in line.lower() and "guidance" in line.lower() and "name" not in line.lower()
    ]
    assert missing == []


def test_the_readme_and_every_page_say_the_same_independence_sentence() -> None:
    """War room F-08 / R8: nothing said the project is independent, under a hostname that carries a company's name. The
    pages read one constant (src/lib/independence.ts); the README states the same sentence."""
    constant = re.search(r'INDEPENDENCE = "([^"]+)"', (ROOT / "src" / "lib" / "independence.ts").read_text(encoding="utf-8"))
    assert constant, "src/lib/independence.ts names the sentence"
    assert constant.group(1) in readme()
