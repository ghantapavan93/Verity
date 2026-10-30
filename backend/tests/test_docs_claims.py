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
import html
import importlib.util
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from app.ingest import PARSER_VERSION
from app.ingest.coverage import PARTS
from app.policy.proof import CARVE_OUT
from app.retrieval.lexical import RETRIEVAL_VERSION
from app.runs.status import POLICY_VERSION
from app.verify.spans import VERIFIER_VERSION

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
README = ROOT / "README.md"
STATUS = ROOT / "docs" / "STATUS.md"

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
    """What the repository states as current: the README, and docs/STATUS.md, which holds the counts and versions the
    README's one screen leaves out (2026-10-30)."""
    return "\n".join(path.read_text(encoding="utf-8") for path in (README, STATUS))


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


# ----------------------------------------------------------------------------- measured figures, derived by code
#
# A figure written into prose is derived by code from committed inputs, or labelled with what it was measured on and
# when. The stress test of 2026-10-30 found that none of the measured figures was held anywhere: CUAD-30's table was the
# scorer's output on an unfaithful unit (0.85 published, 0.81 on the reported answer, EVL-4), the golden figure had no
# code that derived it at all (EVL-2), and the retrieval figure was a superseded configuration's (EVL-6).


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"docs_claims_{name}", BACKEND / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CUAD_RECORDING = BACKEND / "app" / "batch" / "recordings" / "cuad-30-51398ed416634c15.json"


def test_the_cuad_30_table_is_the_committed_recording_scored_by_the_scorer_in_force() -> None:
    """docs/CUAD.md's table and verdict are what scripts/score_cuad.py prints for the committed recording of batch
    51398ed416634c15, row by row, so a change to the unit, the rule or the population that moves a cell fails here."""
    score_cuad = _script("score_cuad")
    recording = score_cuad.load_recording(CUAD_RECORDING)
    scored = score_cuad.score_recording(recording)
    cuad = (ROOT / "docs" / "CUAD.md").read_text(encoding="utf-8")
    for row in score_cuad.table(scored).splitlines():
        assert row in cuad, f"docs/CUAD.md does not carry this row of the scored recording: {row}"
    first, second = score_cuad.verdict(scored, score_cuad.refusals(recording)).splitlines()[:2]
    figures = re.search(r"citation precision (\d\.\d\d) \(floor (\d\.\d\d)\), recall (\d\.\d\d) \(floor (\d\.\d\d)\)", first)
    assert figures, first
    stated = f"citation precision {figures.group(1)} (floor {figures.group(2)}) and recall {figures.group(3)} (floor {figures.group(4)})"
    assert stated in cuad, f"docs/CUAD.md should state the scored verdict's figures: {stated}"
    assert second == "verdict: fit to draft a repository review of these categories" and "so the\nclause lookup is fit to draft" in cuad


GOLDEN_RECORDING = BACKEND / "app" / "goldens" / "recordings" / "6c.json"


def _listed(ids: list[str]) -> str:
    return ids[0] if len(ids) == 1 else ", ".join(ids[:-1]) + f" and {ids[-1]}"


def test_the_golden_figure_is_the_committed_recording_replayed_by_the_code_in_force() -> None:
    """docs/STATUS.md states the golden figure as Recording 6c's answers replayed through the code in force: the count,
    the goldens that fail and the passes a lowered finding carries are the recording file's replayed block, which
    tests/test_goldens.py derives by replaying it. Every other golden count STATUS states names what it was measured
    on. STATUS said "37 of 44 under the current reader", which no code derived, and that the false-premise golden "fails
    today", which no recording since Recording 6c shows (stress test EVL-2)."""
    replayed = json.loads(GOLDEN_RECORDING.read_text(encoding="utf-8"))["replayed"]
    status = " ".join(STATUS.read_text(encoding="utf-8").split())
    figure = f"replayed through the code in force pass {replayed['passes']} of {replayed['of']}, failing {_listed(replayed['fails'])}"
    assert figure in status, f"docs/STATUS.md should state: {figure}"
    lowered = f"{len(replayed['lowered'])} of those {replayed['passes']} passes rest on a finding code lowered ({_listed(replayed['lowered'])})"
    assert lowered in status, f"docs/STATUS.md should state: {lowered}"
    for sentence in sentences(STATUS.read_text(encoding="utf-8")):
        if re.search(r"\b\d+ of 4[24]\b", sentence):
            assert re.search(r"Recording \w+|\bS0\b|replay", sentence), f"a golden count names no recording: {sentence[:160]}"
        if re.search(r"false[- ]premise", sentence) and re.search(r"\bfails\b", sentence):
            assert "g44" in replayed["fails"], f"g44 passes in the replay, and this says it fails: {sentence[:160]}"


RETRIEVAL_RESULTS = BACKEND / "scripts" / "results" / "eval_retrieval-bm25.json"
_FIGURE = re.compile(r"\b0\.\d\d\b|\bBM25 \d+, hybrid \d+")
_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


def undated_figures(text: str) -> list[str]:
    """Clauses that state a measured retrieval figure and name no day it was measured."""
    return [clause for clause in sentences(text) if _FIGURE.search(clause) and not _DATE.search(clause)]


def test_the_retrieval_figure_is_the_committed_measurement_labelled_with_its_configuration() -> None:
    """docs/STATUS.md gave BM25 Recall@6 as 0.85, undated, beside a hybrid's 0.95: the figure of BM25 without the alias
    table, which had made it 0.98 since 2026-10-01 (stress test EVL-6). The figure stated is the committed measurement
    (scripts/eval_retrieval.py --results), with the configuration it was measured under; it may be called the code in
    force only while the code's fingerprint is the file's; and every other retrieval figure in the row names its day."""
    eval_retrieval = _script("eval_retrieval")
    results = json.loads(RETRIEVAL_RESULTS.read_text(encoding="utf-8"))
    bm25 = results["modes"]["bm25"]
    sets, measured_under = bm25["sets"], bm25["fingerprint"]
    row = next(line for line in STATUS.read_text(encoding="utf-8").splitlines() if line.startswith("| Retrieval |"))
    cuad, goldens = sets["CUAD both"], sets["goldens"]
    stated = f"Recall@6 {cuad['R@6']:.2f} on {cuad['cases']} CUAD cases with experts' spans and {goldens['R@6']:.2f} on {goldens['cases']} goldens"
    assert stated in row, f"docs/STATUS.md should state: {stated}"
    under = (
        f"measured {results['measured']} at {measured_under['retrieval_version']}, reader {measured_under['reader']}, "
        f"alias table {measured_under['aliases']}, k = {measured_under['k']}"
    )
    assert under in row, f"docs/STATUS.md should say what the figure was measured under: {under}"
    if "in force" in row:
        assert eval_retrieval.fingerprint("bm25") == measured_under, "the row calls a measurement of other code the code in force"
    assert undated_figures(row) == []


def test_control_the_old_retrieval_row_fails_the_check() -> None:
    old = (
        "| Retrieval | BM25 scored against labels, 164 CUAD cases with experts' spans and 38 goldens: Recall@6 0.85 and 0.92; "
        "a hybrid with a local embedding model measured at 0.95 and 0.97 and built behind a setting; on the 44 goldens BM25 37, "
        "hybrid 40 with one regression, so BM25 stays the default by the rule (`docs/RETRIEVAL.md`) |"
    )
    assert len(undated_figures(old)) == 3


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
    # What the model is shown on every deployment, hosted or not: the ranked sections, the linked ones, the window.
    from app.runs.links import MAX_LINKS

    assert f"shows the model at most {words[k]} chosen by retrieval and {words[MAX_LINKS]} the contract points to" in story
    assert f"each cut at {window:,} characters. Code looks across the rest" in story


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


# The checks policy-v14 added: where a run calls each, and the words that name what it checks. A page or document that
# leaves to a person what code now checks misleads a reader about what a status means: for a day after policy-v14 began
# checking it, the first screen said "whether a condition was left out, code does not check" and the README said it
# "stays a person's call" (2026-10-16). The first version of this test matched that one sentence's word order and missed
# the README. A denial is one of the idioms below: those found where these pages leave a thing to a person or the model
# (src/, the README, docs/ and proof/, read on 2026-10-16), matched in the text as a reader sees it. It is a tripwire for
# the wordings found, not a proof that no other exists: a wording outside the list, a denial split by a semicolon or
# across a table's cells, or one naming the check only by a pronoun passes (DECISIONS.md, 2026-10-16). A check is named
# by its subject's words in any order.
_NOT = r"(?:does not|doesn't|did not|never|cannot|can't|will not|won't)"
_PERSON = r"(?:a |the )?(?:person|reader|reviewer|human)"
DENIAL = re.compile(
    rf"\b(?:code|it|verity|the workbench|the verifier|the policy) {_NOT} (?:check|verify|catch|see|test|look at|tell|decide)"
    r"|\b(?:code|it|verity) never (?:checks|verifies|catches|sees|tests|looks at|decides)"
    r"|\bnot (?:checked|verified|caught|tested|decided)\b|\bunchecked\b|\bnot code's|\bno code check"
    r"|\bthe model's (?:reading|call|judgement|judgment|view|job)"
    rf"|\bleft to (?:the model|{_PERSON})|\b(?:stays|stay|is|are|remains|remain|rests|rest) with {_PERSON}|\b{_PERSON} decides"
    rf"|\b(?:stays|stay|is|are|remains|remain) {_PERSON}(?:'s|s') (?:call|judgement|judgment|reading)"
    r"|\b(?:yours|a person's|a reviewer's|the reader's|the model's) to (?:check|decide|judge)",
    re.IGNORECASE,
)


class DeniedCheck(NamedTuple):
    calls: tuple[tuple[str, str], ...]  # (file under backend/app, call): the run path that performs the check
    subject: tuple[re.Pattern[str], ...]  # every one appears in a statement that names the check
    # A phrase naming more than the check covers ("every condition", "a condition in another clause"): what is said of
    # it is a true limit, so it is set aside before the subject is read, and the rest of the statement still counts.
    scope: re.Pattern[str] | None


DENIED_CHECKS = {
    # check_conditions lowers a pass whose quote leaves out a condition its own sentence opens with a CARVE_OUT word,
    # unless the answer shares enough of its words. Every condition, and conditions in other clauses, are not checked.
    "a condition the quote leaves out of its sentence": DeniedCheck(
        calls=(("runs/service.py", "left_out_condition("), ("runs/service.py", "check_conditions(")),
        subject=(
            re.compile(r"\b(?:condition|exception|carve[- ]out|proviso|qualification)s?\b|[“\"](?:unless|except|subject to)[”\"]", re.IGNORECASE),
            re.compile(
                r"\b(?:left[- ]out|leav(?:es|e|ing) (?:\S+ ){0,3}?out|omit(?:s|ted|ting)?|drop(?:s|ped|ping)?|missing|miss(?:es|ed)?"
                r"|ignor(?:es|ed|ing)?|carr(?:y|ies)|states?|mentions?|includes?|keeps?|repeats?)\b",
                re.IGNORECASE,
            ),
        ),
        scope=re.compile(
            r"\b(?:every|each|all(?: the| its| their)?) (?:condition|exception)s?(?: (?:and|or) (?:condition|exception)s?)?\b"
            r"|\b(?:condition|exception)s? (?:elsewhere|in (?:another|other|a different) (?:section|clause|sentence|part)s?)\b",
            re.IGNORECASE,
        ),
    ),
    # uniform_party_choices, in check_values, lowers a pass that gives one value to every party where the passages
    # give the parties different ones.
    "one value given to every party": DeniedCheck(
        calls=(("runs/service.py", "check_values("), ("runs/status.py", "uniform_party_choices(")),
        subject=(
            re.compile(r"\b(?:one|the same|a single|a shared) (?:value|number|period|deadline|figure|amount)s?\b", re.IGNORECASE),
            re.compile(r"\b(?:every|each|all|both) (?:part(?:y|ies)|side)\b|\bthe parties\b", re.IGNORECASE),
        ),
        scope=None,
    ),
}


def reader_facing() -> list[Path]:
    """What a visitor or a reader of the repository reads as the product's own account of itself (DECISIONS.md is a
    record of what was true when each entry was written, and is not read here)."""
    return [
        *(path for path in (ROOT / "src").rglob("*.ts*") if ".test." not in path.name),
        README,
        *sorted((ROOT / "docs").glob("*.md")),
        ROOT / "proof" / "index.html",
    ]


_HTML_HEADED_LIST = re.compile(r"<h\d[^>]*>([^<]*)</h\d>\s*<[ou]l[^>]*>(.*?)</[ou]l>", re.DOTALL)
# "Not checked by code:" or "### Not checked by code", then the list, a blank line between or not.
_MD_HEADED_LIST = re.compile(r"^(?:([^\n#][^\n]*):|#{1,6}[ \t]+([^\n]+?))[ \t]*\n(?:[ \t]*\n)*((?:[ \t]*[-*] [^\n]*\n?)+)", re.MULTILINE)


def statements(text: str) -> Iterator[str]:
    """Each sentence as a reader sees it (JSX writes "the model&apos;s reading"; one apostrophe for ' and ’), and each
    item of a list read with its heading: /break's "Not checked by the released code" heads a list whose items name what
    is left to a person, and no item says so itself."""
    text = html.unescape(text).replace("’", "'")
    yield from sentences(text)
    for heading, items in _HTML_HEADED_LIST.findall(text):
        for item in re.findall(r"<li[^>]*>(.*?)</li>", items, re.DOTALL):
            yield " ".join(f"{heading}: {item}".split())
    for label, title, items in _MD_HEADED_LIST.findall(text):
        for item in re.findall(r"^[ \t]*[-*] (.*)$", items, re.MULTILINE):
            yield " ".join(f"{label or title}: {item}".split())


def denies(check: DeniedCheck, statement: str) -> bool:
    if not DENIAL.search(statement):
        return False
    rest = check.scope.sub(" ", statement) if check.scope else statement
    return all(word.search(rest) for word in check.subject)


@pytest.mark.parametrize("name", sorted(DENIED_CHECKS))
def test_no_page_or_document_denies_a_check_the_policy_performs(name: str) -> None:
    check = DENIED_CHECKS[name]
    for path, call in check.calls:
        source = (BACKEND / "app" / path).read_text(encoding="utf-8")
        assert call in source, f"app/{path} no longer calls {call!r}: if the check is gone, so must this entry be"
    denials = [
        f"{path.relative_to(ROOT)}: {statement[:160]}"
        for path in reader_facing()
        if path.exists()
        for statement in statements(path.read_text(encoding="utf-8"))
        if denies(check, statement)
    ]
    assert not denials, f"code checks {name} (policy-v14), and these say it does not:\n" + "\n".join(denials)


def test_the_words_the_pages_name_for_the_condition_check_open_a_condition() -> None:
    """The first screen and the README name the words that open a condition the check reads; each must be one
    (policy.proof.CARVE_OUT), or the page promises a check of words code does not read. The sentences say "some passes":
    the rule itself (a sentence's end, the first condition only, how many words the answer must share) is the failure
    envelope's, and a page that states it as "every" overstates it (the review of 2026-10-16)."""
    pages = (ROOT / "src" / "components" / "workbench" / "landing" / "LandingStory.tsx", README)
    for page in pages:
        named = [s for s in sentences(page.read_text(encoding="utf-8")) if "lowers some passes whose quote leaves out" in s]
        assert named, f"{page.name} no longer says which passes the condition check lowers"
        words = [word for s in named for word in re.findall(r"[“\"]([^”\"]+)[”\"]", s)]
        assert words, f"{page.name} names no words that open a condition"
        assert all(CARVE_OUT.fullmatch(word) for word in words), f"{page.name} names {words}; CARVE_OUT reads {CARVE_OUT.pattern}"


def test_the_denial_patterns_catch_the_old_wordings_and_pass_the_true_limits() -> None:
    """Control: what the first screen and the README said at 6574514, and the other ways these pages leave a thing to a
    person, are caught, also beside a true limit; the repaired sentences and the limits still true are not."""
    condition, party = DENIED_CHECKS["a condition the quote leaves out of its sentence"], DENIED_CHECKS["one value given to every party"]
    caught = {
        "Who holds a right, or whether a condition was left out, code does not check.": condition,
        "What a clause means, who holds a right, or whether a condition was left out, stays a person's call.": condition,
        "Who holds a right, whether a condition was left out, or whether the answer carries every condition, stays a person's call.": condition,
        "Code does not check whether the answer leaves out a condition, in this or any other clause.": condition,
        "Whether a condition was left out, here or elsewhere, code does not check.": condition,
        "Whether the answer leaves out a condition is not checked by code.": condition,
        "Whether a condition was left out is not checked.": condition,
        "It does not check whether a condition was left out.": condition,
        "A left-out condition is a person's call.": condition,
        "Whether an exception was omitted is left to a reviewer.": condition,
        "Code never checks whether an answer drops a proviso.": condition,
        "Code does not check whether the answer leaves a condition out.": condition,
        "Whether the answer ignores an exception is the model's reading, not code's.": condition,
        "Whether the answer leaves out a condition is not decided by code.": condition,
        "Whether a condition was left out is the model's view.": condition,
        "A left-out condition stays with a person.": condition,
        "Whether a condition was left out, a person decides.": condition,
        "Code cannot tell whether a condition was left out.": condition,
        "A left-out condition is shown with no code check.": condition,
        "Code doesn’t check whether a condition was left out.": condition,
        "Code doesn&apos;t check whether a condition was left out.": condition,
        "Whether the answer leaves out a condition is the model&apos;s reading, and yours to decide.": condition,
        "Whether a condition was left out is a reviewer&apos;s to check.": condition,
        "Whether the answer drops an “unless” is left to the model.": condition,
        "### Not checked by code\n\n- whether a condition was left out\n": condition,
        "Not checked by code: whether the answer states the exception its quote leaves out": condition,
        "<h3>Not checked by the released code</h3>\n<ul>\n<li>Who holds the right.</li>\n<li>Left-out conditions.</li>\n</ul>": condition,
        "Not checked by code:\n- who holds the right\n- whether a condition was left out\n": condition,
        "Whether one value holds for every party, code does not check.": party,
        "Code does not check whether each party gets the same period.": party,
    }
    for text, check in caught.items():
        assert any(denies(check, s) for s in statements(text)), text
    passed = [
        "A pass is the model's proposal. Code lowers it to review when the evidence shown does not establish it. Code also "
        "lowers some passes whose quote leaves out an “unless”, “except” or “subject to” from its own sentence, where the "
        "answer does not mention it. Whether the answer carries every condition, and who holds a right, code does not check.",
        "What a clause means, who holds a right, and whether an answer carries every condition stay a person's call.",
        "<h3>Not checked by the released code</h3>\n<ul>\n<li>Who holds the right or owes the duty.</li>\n"
        "<li>Whether the answer carries every condition and exception.</li>\n</ul>",
        "Not checked by code: whether the passage supports the answer, including who holds the right or owes the duty",
        "Whether a condition in another clause was left out, code does not check.",
        "The passages state 45 and 60 days. The answer uses 45; which one applies is the model's reading, not checked by code.",
        "The answer quotes wording the contract deletes. Whether it still applies is not decided by code.",
        "Absence is the model's view of the few sections it was handed.",
        "Code checked that each passage is in the document text. Whether it supports the answer is the model&apos;s reading, and yours to decide.",
    ]
    for text in passed:
        assert not any(denies(check, s) for check in DENIED_CHECKS.values() for s in statements(text)), text
