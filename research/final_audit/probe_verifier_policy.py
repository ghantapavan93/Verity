"""Phases 14 and 15: hostile cases for the verifier (bias: a false negative is acceptable, false provenance is not)
and for the deterministic policy (ambiguity must fall to the model's labelled view or to needs review, never to a
confident code-owned pass)."""

from __future__ import annotations

from harness import Report

from app.policy.durations import evaluate, observed_fact, parse_rule
from app.runs.service import verify_evidence
from app.runs.status import decide
from app.verify.spans import locate

r = Report("Phase 14 - verifier hostile cases")
# (name, quote the model gives, text of the document, must_not_verify)
MUST_NOT = [
    ("the rapist vs therapist", "the rapist shall attend", "The therapist shall attend the session."),
    ("therapist vs the rapist", "therapist shall attend", "Neither the rapist shall attend nor the victim."),
    ("un able vs unable", "the party is un able to perform", "If the party is unable to perform its obligations."),
    ("unable vs un able", "the party is unable to perform", "If the party is un able to perform its obligations."),
    ("1 5 days vs 15 days", "within 1 5 days of notice", "Payment is due within 15 days of notice."),
    ("15 days vs 1 5 days", "within 15 days of notice", "Payment is due within 1 5 days of notice."),
    ("15.00 vs 1.5", "a fee of 15.00 percent", "The Customer pays a fee of 1.5 percent."),
    ("15% vs 1.5%", "interest at 15% per month", "Late amounts bear interest at 1.5% per month."),
    ("1.5% vs 15%", "interest at 1.5% per month", "Late amounts bear interest at 15% per month."),
    ("Section 1.1 vs Section 11", "as set out in Section 1.1", "The fees are as set out in Section 11 of this Agreement."),
    ("Section 12.1 vs Section 1.21", "under Section 12.1", "Liability under Section 1.21 is capped."),
    ("30 days vs 130 days", "within 30 days", "Payment is due within 130 days of invoice."),
    ("$1,500 vs $11,500", "capped at $1,500", "Liability is capped at $11,500 in aggregate."),
    ("$1,000 vs EUR 1,000", "a fee of $1,000", "The Customer pays a fee of €1,000 per month."),
    ("USD 1,000 vs GBP 1,000", "a fee of USD 1,000", "The Customer pays a fee of GBP 1,000 per month."),
    ("not dropped", "Customer may assign this Agreement", "Customer may not assign this Agreement without consent."),
    ("shall vs shall not", "Provider shall not be liable", "Provider shall be liable for direct damages."),
    ("word inside a word", "able to perform", "The party is unable to perform."),
    ("changed digit", "ninety (90) days", "ninety (60) days prior written notice"),
    ("007 vs 7", "within 007 days", "Notice is effective within 7 days."),
    ("7 vs 007", "form 7 applies", "Use form 007 applies in all cases."),
]
for name, quote, text in MUST_NOT:
    found = locate(quote, text, "1 Clause")
    r.check(
        f"must not verify: {name}",
        found is None,
        "" if found is None else f"VERIFIED by {found.method} at {found.start}-{found.end}: {text[found.start : found.end]!r}",
    )

# Cases where forgiving is the documented behaviour: report what happens and why it is not false provenance.
REPORT = [
    ("30days vs 30 days (lost space between a number and a word)", "within 30days of receipt", "Payment is due within 30 days of receipt."),
    ("30 days vs 30days", "within 30 days of receipt", "Payment is due within 30days of receipt."),
    ("1500 vs 1,500 (same value)", "a cap of 1500 dollars", "Liability has a cap of 1,500 dollars."),
    ("1,500 vs 1500", "a cap of 1,500 dollars", "Liability has a cap of 1500 dollars."),
    ("OCR split: terminat ion", "terminat ion for convenience", "This is termination for convenience."),
    ("OCR join: writtennotice", "prior writtennotice to the other", "upon prior written notice to the other party"),
    ("Arabic-Indic digits for 30", "within ٣٠ days", "Payment is due within 30 days."),
    ("fullwidth digits for 30", "within ３０ days", "Payment is due within 30 days."),
    ("curly vs straight apostrophe", "days' written notice", "sixty (60) days’ written notice"),
    ("case difference", "EITHER PARTY MAY TERMINATE", "Either party may terminate this Agreement."),
]
for name, quote, text in REPORT:
    found = locate(quote, text, "1 Clause")
    r.note(name, "INFO", "not verified" if found is None else f"verified by {found.method}: {text[found.start : found.end]!r}")

twice = "Either party may terminate. Either party may terminate. The end."
found = locate("Either party may terminate.", twice, "1 Clause")
r.check("a quote that occurs twice reports that it does", found is not None and found.count == 2, f"count {found.count if found else None}")


class Sec:
    def __init__(self, ordinal: int, number: str, heading: str, text: str) -> None:
        self.ordinal, self.number, self.heading, self.text, self.id = ordinal, number, heading, text, f"s{ordinal}"


long_text = ("Preamble sentence. " * 300) + "The notice period is sixty (60) days." + (" Trailer." * 10)
inside, beyond = Sec(0, "1", "Long", long_text), Sec(1, "2", "Other", "Nothing relevant here.")
position = long_text.index("The notice period")
section, located, method = verify_evidence("The notice period is sixty (60) days.", "sec_0", {"sec_0": inside, "sec_1": beyond}, [inside, beyond], window=5000)  # type: ignore[dict-item,list-item]
r.check(f"a quote at offset {position}, beyond a 5000-char window, is not provenance the model had", located is None, method)
section, located, method = verify_evidence("The notice period is sixty (60) days.", "sec_0", {"sec_0": inside, "sec_1": beyond}, [inside, beyond], window=6000)  # type: ignore[dict-item,list-item]
r.check("the same quote inside a 6000-char window verifies", located is not None, method)
elsewhere = Sec(7, "8", "Not handed over", "The notice period is sixty (60) days.")
section, located, method = verify_evidence("The notice period is sixty (60) days.", "sec_7", {"sec_1": beyond}, [beyond], window=5000)  # type: ignore[dict-item,list-item]
r.check("a quote that exists only in a section the model was not handed is not verified", located is None, method)
r.done()

# ------------------------------------------------------------------------------------------------ Phase 15
r = Report("Phase 15 - policy hostile cases")
TOPIC = "Termination for convenience"


def run(guidance: str, quote: str, hint: str = "pass", observed: str | None = None, required: str | None = None, topic: str = TOPIC):  # type: ignore[no-untyped-def]
    return decide(hint, observed, required, True, True, quotes=[quote], guidance=guidance, topic=topic)  # type: ignore[arg-type]


# (name, guidance, quote, expected (status, source) or a set of acceptable outcomes)
SAFE = {("needs_review", "ambiguous_fact"), ("needs_review", "position_check"), ("needs_review", "computed_days")}
HINT = ("pass", "model_hint")
CASES = [
    (
        "at least 90, contract 60",
        "We require at least 90 days' written notice for termination for convenience.",
        "terminate upon sixty (60) days' written notice",
        {("needs_review", "computed_days")},
    ),
    (
        "at least 90, contract 90",
        "We require at least 90 days' written notice for termination for convenience.",
        "terminate for convenience upon ninety (90) days' written notice",  # names the subject: a pass by code needs that since policy-v2
        {("pass", "confirmed_days")},
    ),
    (
        "not less than 90, contract 60",
        "Termination for convenience requires not less than 90 days' notice.",
        "terminate upon 60 days' written notice",
        {("needs_review", "computed_days")},
    ),
    (
        "no fewer than 90, contract 120",
        "Termination for convenience requires no fewer than 90 days' notice.",
        "terminate for convenience upon 120 days' written notice",
        {("pass", "confirmed_days")},
    ),
    (
        "at most 30, contract 60",
        "Termination for convenience notice must be at most 30 days.",
        "terminate upon 60 days' written notice",
        {("needs_review", "computed_days")},
    ),
    (
        "no more than 30, contract 15",
        "Termination for convenience notice must be no more than 30 days.",
        "terminate for convenience upon 15 days' written notice",
        {("pass", "confirmed_days")},
    ),
    (
        "prior written notice of 90",
        "Termination for convenience needs 90 days' prior written notice.",
        "upon sixty (60) days prior written notice",
        {("needs_review", "computed_days"), HINT},
    ),
    (
        "business vs calendar: 60 business days against 90 calendar",
        "We require at least 90 calendar days' notice for termination for convenience.",
        "terminate upon 60 business days' notice",
        SAFE | {HINT},
    ),
    (
        "business vs calendar: 90 business days against 90 calendar",
        "We require at least 90 calendar days' notice for termination for convenience.",
        "terminate upon 90 business days' notice",
        {("pass", "confirmed_days"), HINT} | SAFE,
    ),
    (
        "one month against 30 days",
        "We require at least 30 days' notice for termination for convenience.",
        "terminate upon one month's written notice",
        SAFE | {HINT},
    ),
    (
        "three months against 90 days",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon three (3) months' written notice",
        SAFE | {HINT, ("pass", "confirmed_days")},
    ),
    (
        "range in the contract: 30 to 60 days",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon 30 to 60 days' written notice",
        SAFE | {HINT},
    ),
    (
        "earlier of two periods",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon the earlier of 30 days or 90 days after notice",
        SAFE | {HINT},
    ),
    (
        "later of two periods",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon the later of 30 days or 120 days after notice",
        SAFE | {HINT},
    ),
    (
        "unless clause shortens it",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon 90 days' notice, unless the other party is in breach, in which case 10 days",
        SAFE | {HINT},
    ),
    (
        "except clause",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon 120 days' notice except that Customer may terminate on 5 days' notice",
        SAFE | {HINT},
    ),
    (
        "words and digits disagree",
        "We require at least 90 days' notice for termination for convenience.",
        "terminate upon ninety (60) days' written notice",
        {("needs_review", "ambiguous_fact")} | SAFE,
    ),
    (
        "guidance has two topics",
        "Payment within 30 days. Termination for convenience requires at least 90 days' notice.",
        "terminate upon sixty (60) days' written notice",
        {("needs_review", "computed_days")},
    ),
    (
        "guidance has two topics, finding is about payment",
        "Payment within 30 days. Termination for convenience requires at least 90 days' notice.",
        "invoices are payable within sixty (60) days",
        SAFE | {HINT},
    ),
    (
        "guidance with two durations for one topic",
        "Termination for convenience: at least 90 days, or 30 days for pilots.",
        "terminate upon sixty (60) days' written notice",
        SAFE | {HINT},
    ),
    ("no duration in the guidance", "Termination for convenience must be mutual.", "terminate upon sixty (60) days' written notice", {HINT}),
    (
        "no duration in the quote",
        "We require at least 90 days' notice for termination for convenience.",
        "Either party may terminate this Agreement for convenience.",
        {HINT},
    ),
    (
        "immediately",
        "We require at least 90 days' notice for termination for convenience.",
        "Either party may terminate this Agreement immediately upon notice.",
        SAFE | {HINT},
    ),
]
dangerous = 0
for name, guidance, quote, acceptable in CASES:
    topic = "Payment terms" if "about payment" in name else TOPIC
    d = run(guidance, quote, topic=topic)
    ok = (d.status, d.source) in acceptable
    # The dangerous outcome is a confident code-owned pass where the contract is not clearly within the guidance.
    r.check(name, ok, f"{d.status} / {d.source}" + (f" · {d.reason}" if d.reason else ""))
    if not ok and d.status == "pass" and d.source in ("computed_days", "confirmed_days"):
        dangerous += 1
r.note("confident code-owned passes outside the acceptable set", "INFO", str(dangerous))

# The model's own stated numbers cannot move the result.
d = run(
    "We require at least 90 days' notice for termination for convenience.",
    "terminate upon sixty (60) days' written notice",
    observed="90 days' notice",
    required="at least 90 days",
)
r.check(
    "the model states 90 where the quote says 60: lowered, not passed", d.status == "needs_review" and d.source == "position_check", f"{d.status} / {d.source}"
)
d = run(
    "We require at least 90 days' notice for termination for convenience.",
    "terminate upon sixty (60) days' written notice",
    observed="60 days",
    required="at least 30 days",
)
r.check(
    "the model states a requirement the guidance does not carry: lowered",
    d.status == "needs_review" and d.source == "position_check",
    f"{d.status} / {d.source}",
)
d = decide("pass", None, None, True, False, quotes=[], guidance="at least 90 days", topic=TOPIC)
r.check("an unverified quote decides nothing: unresolved", d.status == "unresolved" and d.source == "no_evidence")
for label, guidance, quote in [
    ("rule", "at least 90 days' notice for termination for convenience", "sixty (60) days"),
    ("rule", "no more than 30 days' notice for termination", "15 days"),
]:
    rule, fact = parse_rule(guidance, TOPIC), observed_fact(quote)
    r.note(f"parsed {label}", "INFO", f"{guidance!r} -> {rule} | {quote!r} -> {fact} | {evaluate(fact, rule).outcome}")
r.done()
