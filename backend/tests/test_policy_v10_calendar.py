"""policy-v10: periods in units that do not convert are placed on the calendar, and Business Days are read from the
contract's own definition (policy.durations.calendar_days, business_week).

The ranges are checked against brute-force calendars, never against the formulas that produce them: every start
weekday and random public holidays for business days, random start dates over three centuries for months and years.
The decisions are checked where the legal pilot failed (H4-Q5: 30 days "met" 30 Business Days) and in both directions,
with and without a definition, and through the API on a contract that defines a Business Day far from the clause."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.policy.durations import BusinessWeek, Duration, DurationUnit, Span, business_week, calendar_days, day_convention, evaluate, observed_fact, parse_rule
from app.providers.base import Generation
from app.runs.status import POLICY_VERSION, decide
from tests.support import FUZZ_SCALE, FakeProvider

WEEKDAYS = BusinessWeek(5, '"Business Day" means any day other than a Saturday, a Sunday or a public holiday.', "§1.1")
# The fresh DOCX of the first-visitor acceptance test (2026-10-14), its definition as the reader stored it.
ACCEPTANCE_DEFINITION = (
    '"Business Day" means a Monday, Tuesday, Wednesday, Thursday or Friday, excluding (a) any day on which commercial banks '
    "in Portland, Maine are authorized or required by law to close and (b) 31 December in each year; and where a public "
    "holiday in the State of Maine falls on a Saturday or Sunday, the next following Monday is also not a Business Day."
)


def _span_of_business_days(start: date, count: int, weekend: set[int], holidays: set[date]) -> int:
    """Calendar days from ``start`` until the ``count``-th business day after it, counted one day at a time."""
    day, seen = start, 0
    while seen < count:
        day += timedelta(days=1)
        if day.weekday() not in weekend and day not in holidays:
            seen += 1
    return (day - start).days


@settings(max_examples=60 * FUZZ_SCALE, deadline=None)
@given(count=st.integers(1, 260), weekend=st.sampled_from([{5, 6}, {4, 5}, {6}]))
def test_business_days_take_at_least_the_bound_on_some_start_and_never_fewer(count: int, weekend: set[int]) -> None:
    week = BusinessWeek(7 - len(weekend), "", "")
    span = calendar_days(Duration(Decimal(count), DurationUnit.BUSINESS_DAY), week)
    assert span is not None and span.hi is None
    spans = [_span_of_business_days(date(2031, 3, 1) + timedelta(days=offset), count, weekend, set()) for offset in range(7)]
    assert min(spans) == span.lo  # the bound is reached on some start weekday: it is the bound, not a guess below it


@settings(max_examples=40 * FUZZ_SCALE, deadline=None)
@given(count=st.integers(1, 120), offset=st.integers(0, 3000), holidays=st.sets(st.integers(0, 400), max_size=40))
def test_public_holidays_only_lengthen_business_days(count: int, offset: int, holidays: set[int]) -> None:
    start = date(2030, 1, 1) + timedelta(days=offset)
    span = calendar_days(Duration(Decimal(count), DurationUnit.BUSINESS_DAY), WEEKDAYS)
    assert span is not None
    assert _span_of_business_days(start, count, {5, 6}, {start + timedelta(days=h) for h in holidays}) >= span.lo


def _months_later(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


@settings(max_examples=150 * FUZZ_SCALE, deadline=None)
@given(months=st.integers(1, 240), start=st.dates(date(1901, 1, 1), date(2199, 12, 31)))
def test_months_take_a_range_every_calendar_falls_within(months: int, start: date) -> None:
    span = calendar_days(Duration(Decimal(months), DurationUnit.MONTH), None)
    assert span is not None and span.hi is not None
    assert span.lo <= (_months_later(start, months) - start).days <= span.hi


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1, DurationUnit.MONTH, Span(Decimal(28), Decimal(31))),
        (2, DurationUnit.MONTH, Span(Decimal(59), Decimal(62))),
        (3, DurationUnit.MONTH, Span(Decimal(89), Decimal(92))),
        (12, DurationUnit.MONTH, Span(Decimal(365), Decimal(366))),
        (1, DurationUnit.YEAR, Span(Decimal(365), Decimal(366))),
        (4, DurationUnit.YEAR, Span(Decimal(1460), Decimal(1461))),  # four years without a leap day: across 2100
        (30, DurationUnit.BUSINESS_DAY, Span(Decimal(40), None)),
        (5, DurationUnit.BUSINESS_DAY, Span(Decimal(5), None)),
        (6, DurationUnit.BUSINESS_DAY, Span(Decimal(8), None)),
        (2, DurationUnit.WEEK, Span(Decimal(14), Decimal(14))),
    ],
)
def test_known_ranges(value: int, unit: DurationUnit, expected: Span) -> None:
    assert calendar_days(Duration(Decimal(value), unit), WEEKDAYS) == expected


def test_what_code_cannot_place_it_does_not_place() -> None:
    assert calendar_days(Duration(Decimal(30), DurationUnit.BUSINESS_DAY), None) is None  # no definition
    assert calendar_days(Duration(Decimal("1.5"), DurationUnit.MONTH), None) is None
    assert calendar_days(Duration(Decimal(700), DurationUnit.MONTH), None) is None  # past fifty years


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ('"Business Day" means any day other than a Saturday, a Sunday or a day on which banks in New York are closed.', 5),
        ("“Business Day” means a day (other than a Saturday or Sunday) on which banks are open in London.", 5),
        ("Business Days shall mean Monday through Friday, excluding public holidays in England.", 5),
        ('"Working Day" means any day which is not a weekend or a bank holiday in Ireland.', 5),
        ('"Business Day" means any day other than a Sunday or a public holiday in India.', 6),
        # The days a definition names, however it names them (first-visitor acceptance test, 2026-10-14): the original
        # listed its weekdays, and code said the contract did not define a Business Day by the days of the week.
        (ACCEPTANCE_DEFINITION, 5),
        ('"Business Day" means any of Monday, Tuesday, Wednesday, Thursday and Friday, other than a bank holiday.', 5),
        ('"Business Day" means Sunday through Thursday, excluding public holidays in the UAE.', 5),
        ('"Working Day" means Monday to Saturday (inclusive) other than a gazetted holiday.', 6),
        ("Business Days shall mean Mondays to Fridays, excluding public holidays in England.", 5),
        ('"Business Day" means Monday–Friday except a federal holiday.', 5),
        # An exclusion list that runs on past semicolons is read to its end.
        ('"Business Day" means a day other than (a) a Saturday; (b) a Sunday; or (c) a public holiday in England.', 5),
    ],
)
def test_a_definition_that_fixes_the_week_is_read(text: str, days: int) -> None:
    week = business_week([("§1.1", "1.1 Definitions. " + text)])
    assert week is not None and (week.days, week.where) == (days, "§1.1") and "mean" in week.sentence


@pytest.mark.parametrize(
    "sections",
    [
        [("§1", '"Business Day" means a day on which commercial banks are open for general business in London.')],
        [("§1", '"Business Day" means any day, including a Saturday, other than a Sunday or a public holiday.')],
        [("§1", "The Seller shall respond within five Business Days.")],  # used, never defined
        [
            ("§1", '"Business Day" means any day other than a Saturday or Sunday.'),
            ("Schedule 2", '"Business Day" means any day other than a Sunday.'),
        ],  # two definitions that disagree
        [],
        # Controls for the days a definition names: one day alone, days the next definition names, a semicolon that
        # opens another definition rather than the next item of a list.
        [("§1", '"Business Day" means a Monday on which banks are open.')],
        [("§1", '"Business Day" means a day on which banks in London are open; "Weekend" means a Saturday and a Sunday.')],
        [("§1", '"Business Day" means a day other than (a) a Saturday; "Sunday Rate" means the rate in Schedule 2.')],
    ],
)
def test_no_week_is_read_where_the_contract_does_not_fix_one(sections: list[tuple[str, str]]) -> None:
    assert business_week(sections) is None


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@settings(max_examples=80 * FUZZ_SCALE, deadline=None)
@given(days=st.lists(st.sampled_from(_DAYS), min_size=2, max_size=7, unique=True), joiner=st.sampled_from(["or", "and"]), plural=st.booleans())
def test_a_list_of_days_is_read_as_that_many(days: list[str], joiner: str, plural: bool) -> None:
    named = [f"{d}s" if plural else d for d in days]
    listed = f"{', '.join(named[:-1])} {joiner} {named[-1]}"
    week = business_week([("§1.1", f'"Business Day" means a {listed}, excluding any public holiday.')])
    assert week is not None and week.days == len(days)


@settings(max_examples=80 * FUZZ_SCALE, deadline=None)
@given(first=st.integers(0, 6), last=st.integers(0, 6), joiner=st.sampled_from(["to", "through", "-", "–", "until"]))
def test_a_run_of_days_is_read_inclusively_around_the_week(first: int, last: int, joiner: str) -> None:
    week = business_week([("§1.1", f'"Business Day" means {_DAYS[first]} {joiner} {_DAYS[last]}, other than a public holiday.')])
    assert week is not None and week.days == (last - first) % 7 + 1


def test_the_acceptance_case_is_codes_shortfall_on_any_calendar() -> None:
    """6 Business Days against at most 7 calendar days, the contract listing its weekdays: at least 8 calendar days."""
    week = business_week([("§1.1", ACCEPTANCE_DEFINITION)])
    quote = ["Supplier fails to remedy it within six (6) Business Days after receiving a Breach Notice;"]
    guidance = (
        "For a safety-critical defect, the supplier's cure period before we may terminate must not exceed 7 calendar days "
        "after the supplier receives our notice."
    )
    decision = decide("pass", "6 Business Days", "not exceed 7 calendar days", True, True, quote, guidance, "Cure period for safety-critical defect", week=week)
    assert (decision.status, decision.source) == ("needs_review", "computed_days")
    assert "at least 8 calendar days, a Business Day as §1.1 defines it" in decision.reason


# ------------------------------------------------------------------------------------------------ decisions

H4_Q5_GUIDANCE = "Seller must be given at least thirty (30) Business Days to dispute the Closing Statement."
H4_Q5_QUOTE = ["Seller may dispute the Closing Statement by written notice to Buyer within thirty (30) days after receiving it."]


def test_the_pilots_business_day_error_is_codes_shortfall_where_the_contract_defines_a_business_day() -> None:
    assert POLICY_VERSION == "policy-v13"  # v11 to v13 keep the v10 calendar
    required = "at least thirty (30) Business Days"
    decision = decide("pass", "thirty (30) days", required, True, True, H4_Q5_QUOTE, H4_Q5_GUIDANCE, "Dispute Period", week=WEEKDAYS)
    assert (decision.status, decision.source) == ("needs_review", "computed_days")
    assert "at least 40 calendar days, a Business Day as §1.1 defines it" in decision.reason and "falls short on any calendar" in decision.reason


def test_without_a_definition_it_goes_to_a_person_and_says_what_a_weekday_reading_would_mean() -> None:
    decision = decide("pass", "thirty (30) days", "at least thirty (30) Business Days", True, True, H4_Q5_QUOTE, H4_Q5_GUIDANCE, "Dispute Period")
    assert (decision.status, decision.source) == ("needs_review", "position_check")
    # What code could not read, never that the contract has no definition (acceptance test, 2026-10-14).
    assert "code could not read from the contract which days of the week are Business Days" in decision.reason
    assert "does not define" not in decision.reason and "If a Business Day is a weekday" in decision.reason


@pytest.mark.parametrize(
    ("quote", "guidance", "week", "expected"),
    [
        # Business days in the contract that meet a floor in days on every calendar: the pass stays the model's.
        ("Buyer shall give ten (10) Business Days' notice.", "Notice of at least 12 days is required.", WEEKDAYS, ("pass", "model_hint")),
        ("Buyer shall give ten (10) Business Days' notice.", "Notice of at least 12 days is required.", None, ("needs_review", "position_check")),
        ("Buyer shall give ten (10) Business Days' notice.", "Notice of at least 15 days is required.", WEEKDAYS, ("needs_review", "position_check")),
        # Months: in order when the ranges are, overlapping otherwise.
        ("Either party may terminate on one (1) month's notice.", "Termination requires at least 45 days' notice.", None, ("needs_review", "computed_days")),
        ("Either party may terminate on three (3) months' notice.", "Termination requires at least 60 days' notice.", None, ("pass", "model_hint")),
        ("Either party may terminate on one (1) month's notice.", "Termination requires at least 30 days' notice.", None, ("needs_review", "position_check")),
        ("Invoices are payable within two (2) months.", "Payment terms must not exceed 90 days.", None, ("pass", "model_hint")),
        ("Invoices are payable within one (1) year.", "Payment terms must not exceed 90 days.", None, ("needs_review", "computed_days")),
    ],
)
def test_periods_on_the_calendar_decide_only_what_every_calendar_agrees_on(
    quote: str, guidance: str, week: BusinessWeek | None, expected: tuple[str, str]
) -> None:
    decision = decide("pass", None, None, True, True, [quote], guidance, "Notice", week=week)
    assert (decision.status, decision.source) == expected, decision.reason
    if expected == ("pass", "model_hint"):
        # Never code's pass (policy-v3): the reason places both periods on the calendar, and the lexical checks still run.
        assert decision.reason.startswith("the contract provides") and "calendar days" in decision.reason


def test_same_unit_and_exact_units_decide_as_before() -> None:
    rule = parse_rule("Termination requires at least 30 days' notice.")
    for quote, outcome in (("fifteen (15) days", "needs_review"), ("five (5) weeks", "pass"), ("thirty (30) days", "pass")):
        fact = observed_fact(quote)
        assert evaluate(fact, rule).outcome == evaluate(fact, rule, WEEKDAYS).outcome == outcome


# ------------------------------------------------------------------------------------------------ through the API

CONTRACT_WITH_DEFINITION = """ASSET PURCHASE AGREEMENT

1. Definitions
1.1 "Business Day" means any day other than a Saturday, a Sunday or a day on which banks in New York are authorised to close.
1.2 "Closing Statement" means the statement delivered under Section 7.

2. Purchase Price
The Purchase Price is $40,000,000, subject to adjustment under Section 7.

7. Closing Statement
7.1 Buyer shall deliver the Closing Statement within sixty (60) days after the Closing.
7.2 Seller may dispute the Closing Statement by written notice to Buyer within thirty (30) days after receiving it.
"""


class DisputeProvider(FakeProvider):
    """Answers as the pilot's model did on H4-Q5: 30 days, said to meet 30 Business Days."""

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        self.calls.append(user)
        label = re.search(r"\[(sec_\d+)\] 7 Closing Statement", user)
        assert label, "§7 was not handed to the model"
        quote = "Seller may dispute the Closing Statement by written notice to Buyer within thirty (30) days after receiving it."
        payload = {
            "findings": [
                {
                    "topic": "Dispute period",
                    "conclusion": f"Seller has 30 days to dispute the Closing Statement, which meets the guidance. [{label.group(1)}]",
                    "status_hint": "pass",
                    "evidence": [{"section_id": label.group(1), "quote": quote}],
                    "guidance_reference": "at least thirty (30) Business Days",
                    "observed": "thirty (30) days",
                    "required": "at least thirty (30) Business Days",
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def test_a_contract_s_own_definition_far_from_the_clause_decides_the_shortfall(client: TestClient) -> None:
    client.app.state.provider = DisputeProvider()  # type: ignore[attr-defined]
    uploaded = client.post("/api/documents", files={"file": ("apa.txt", CONTRACT_WITH_DEFINITION.encode("utf-8"), "text/plain")}).json()
    guidance = client.post("/api/guidance", json={"text": H4_Q5_GUIDANCE}).json()
    question = "How long does Seller have to dispute the Closing Statement?"
    started = client.post("/api/runs", json={"documentId": uploaded["id"], "guidanceId": guidance["id"], "question": question})
    assert started.status_code == 202, started.text
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "computed_days")
    assert "a Business Day as §1.1 defines it" in finding["statusReason"]


# ------------------------------------------------------------------------------------------------ what "days" means


def test_a_contract_that_says_its_days_are_business_days_is_read_so() -> None:
    """An unfamiliar licence (retrieval study, 2026-10-14) says "a reference in this Agreement to 'days' is to Business
    Days"; its royalty reports are due "within forty-five (45) days", and code reported "the contract provides 45
    calendar days". It now reads them as the contract does, and says where."""
    stated = "1.2 Interpretation. Unless expressly stated otherwise, a reference in this Agreement to “days” is to Business Days."
    days = day_convention([("Schedule 1", stated)])
    assert days is not None and days.unit is DurationUnit.BUSINESS_DAY and days.where == "§1.2"
    quote = ["Within forty-five (45) days after the end of each Calendar Quarter, Licensee shall deliver a royalty report."]
    guidance = "Royalty reports must be allowed at least 30 calendar days."
    decision = decide("pass", None, None, True, True, quote, guidance, "Royalty report", week=WEEKDAYS, days=days)
    assert "45 business days (at least 61 calendar days" in decision.reason and '"days" are Business Days in this contract (§1.2)' in decision.reason
    assert "45 calendar days" not in decision.reason


def test_control_calendar_days_said_so_and_a_calendar_convention_are_read_as_calendar_days() -> None:
    days = day_convention([("§1", "1.3 Interpretation. A reference in this Agreement to “days” is to Business Days.")])
    quote = ["Within thirty (30) calendar days after delivery."]
    said = decide("pass", None, None, True, True, quote, "At least 30 days is required.", "Notice", week=WEEKDAYS, days=days)
    assert said.reason.startswith("the contract provides 30 calendar days")
    calendar = day_convention([("§9", '(iv) the word "days" means "calendar days," unless otherwise stated;')])
    assert calendar is not None and calendar.unit is DurationUnit.CALENDAR_DAY
    plain = decide("pass", None, None, True, True, ["within thirty (30) days"], "At least 30 days is required.", "Notice", days=calendar)
    assert plain.reason.startswith("the contract provides 30 calendar days")


def test_no_convention_is_read_where_the_contract_states_two() -> None:
    assert day_convention([("§1", 'A reference to "days" is to Business Days.'), ("§9", 'The word "days" means "calendar days".')]) is None
