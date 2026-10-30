"""The hourly bounds on one network hold for IPv6 (security audit, 2026-10-30).

Every hourly window counted by the full address Cloudflare reported. A subscriber is commonly given an IPv6 /64, 2^64
addresses, so one host could take a fresh address for every visit, upload or question and no window would ever fill.
The windows now count by `client_network`: an IPv4 address itself, an IPv6 address's /64. This reverses the earlier
decision to keep them per full address (war room F-32) on the owner's instruction that abuse must not get through.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import access
from tests.test_anonymous import Visitor, arrive
from tests.test_quota_admission import _with_document


def test_one_ipv6_network_shares_its_visit_window_whatever_address_it_takes(public: TestClient) -> None:
    statuses = [arrive(public, address=f"2001:db8:aa:bb::{n:x}")[1].status_code for n in range(1, access.VISIT_LIMIT + 2)]
    assert statuses[: access.VISIT_LIMIT] == [200] * access.VISIT_LIMIT
    assert statuses[-1] == 429


def test_control_another_ipv6_network_and_ipv4_addresses_keep_their_own(public: TestClient) -> None:
    for n in range(1, access.VISIT_LIMIT + 1):
        assert arrive(public, address=f"2001:db8:aa:bb::{n:x}")[1].status_code == 200
    assert arrive(public, address="2001:db8:aa:cc::1")[1].status_code == 200  # the next /64
    assert arrive(public, address="198.51.100.7")[1].status_code == 200
    assert arrive(public, address="198.51.100.8")[1].status_code == 200  # IPv4: an address is its own network


# ---------------------------------------------------------------------------- reads that are large next to the request
# A run's evidence pack carries the original file (up to 25 MB) and was zipped again on every request, and a document's
# full text came back whole, with no bound on either: one visitor who uploaded once could ask for the same 26 MB pack in
# a loop, holding the upload link and the request threads the health probe also needs (security audit, 2026-10-30).


def _visitor_with_run(public: TestClient) -> tuple[Visitor, str, str]:
    visitor, document_id = _with_document(public)
    started = visitor.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": "What notice applies?"})
    assert started.status_code == 202, started.text
    return visitor, document_id, started.json()["id"]


def test_a_network_asking_for_packs_in_a_loop_is_told_to_wait(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.address_packs, "limit", 3)
    visitor, _, run_id = _visitor_with_run(public)
    codes = [visitor.get(f"/api/runs/{run_id}/evidence-pack").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_a_network_reading_a_contract_in_a_loop_is_told_to_wait(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.address_document_reads, "limit", 3)
    visitor, document_id, _ = _visitor_with_run(public)
    codes = [visitor.get(f"/api/documents/{document_id}").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_packs_are_built_a_few_at_a_time(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    visitor, _, run_id = _visitor_with_run(public)
    for _ in range(access.PACKS_AT_ONCE):
        assert access.packs_building.acquire(blocking=False)  # as many packs as may be built at once, being built
    try:
        refused = visitor.get(f"/api/runs/{run_id}/evidence-pack")
        assert refused.status_code == 503 and refused.headers["Retry-After"]
    finally:
        for _ in range(access.PACKS_AT_ONCE):
            access.packs_building.release()
    assert visitor.get(f"/api/runs/{run_id}/evidence-pack").status_code == 200  # control: with room, it is built


def test_control_the_owner_store_is_not_bounded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.address_packs, "limit", 1)
    from tests.support import upload_and_ask

    run_id = upload_and_ask(client, "What notice applies?")["run_id"]
    assert [client.get(f"/api/runs/{run_id}/evidence-pack").status_code for _ in range(3)] == [200, 200, 200]


def test_a_refused_or_unknown_pack_spends_none_of_the_hour(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # The hourly pack slot was taken before the run was looked up and before a pack could be built, so a 404 or a 503
    # ("try again in a few seconds") spent one of the thirty (fresh review, 2026-10-30).
    monkeypatch.setattr(access.address_packs, "limit", 1)
    visitor, _, run_id = _visitor_with_run(public)
    assert visitor.get("/api/runs/no-such-run/evidence-pack").status_code == 404
    for _ in range(access.PACKS_AT_ONCE):
        assert access.packs_building.acquire(blocking=False)
    try:
        assert visitor.get(f"/api/runs/{run_id}/evidence-pack").status_code == 503
    finally:
        for _ in range(access.PACKS_AT_ONCE):
            access.packs_building.release()
    assert visitor.get(f"/api/runs/{run_id}/evidence-pack").status_code == 200  # the one slot was still there
    assert visitor.get(f"/api/runs/{run_id}/evidence-pack").status_code == 429  # control: and now it is spent


# ---------------------------------------------------------------------------- reads that redo document-wide work
# A run's trust manifest locates every span in every section of the document again, and its revision check compares
# every loose section pair: a GET of either cost seconds to minutes and up to gigabytes, and neither had a bound of any
# kind (stress test, 2026-10-30: one visitor's GET /trust/diff on two 2,500-section versions took 15 s and 1.2 GB, and
# three at once three times that). They are now built a few at a time and count as contract views.


def _visitor_with_revision(public: TestClient) -> tuple[Visitor, str, str]:
    from tests.test_trust import REVISED

    visitor, first, run_id = _visitor_with_run(public)
    second = visitor.post("/api/documents", files={"file": ("agreement-v2.txt", REVISED.encode("utf-8"), "text/plain")})
    assert second.status_code == 201, second.text
    later = second.json()["id"]
    assert visitor.post(f"/api/documents/{later}/supersedes", json={"previousDocumentId": first}).status_code == 201
    return visitor, run_id, later


@pytest.mark.parametrize("kind", ["trust", "diff"])
def test_a_network_asking_for_a_trust_read_in_a_loop_is_told_to_wait(public: TestClient, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    monkeypatch.setattr(access.address_document_reads, "limit", 3)
    visitor, run_id, later = _visitor_with_revision(public)
    path = f"/api/runs/{run_id}/trust" if kind == "trust" else f"/api/runs/{run_id}/trust/diff?documentId={later}"
    codes = [visitor.get(path).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


@pytest.mark.parametrize("kind", ["trust", "diff"])
def test_trust_reads_are_built_a_few_at_a_time(public: TestClient, kind: str) -> None:
    visitor, run_id, later = _visitor_with_revision(public)
    path = f"/api/runs/{run_id}/trust" if kind == "trust" else f"/api/runs/{run_id}/trust/diff?documentId={later}"
    for _ in range(access.TRUST_READS_AT_ONCE):
        assert access.trust_reads_building.acquire(blocking=False)
    try:
        refused = visitor.get(path)
        assert refused.status_code == 503 and refused.headers["Retry-After"]
    finally:
        for _ in range(access.TRUST_READS_AT_ONCE):
            access.trust_reads_building.release()
    assert visitor.get(path).status_code == 200  # control: with room, it is built


def test_a_refused_or_unknown_trust_read_spends_none_of_the_hour(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.address_document_reads, "limit", 1)
    visitor, run_id, _ = _visitor_with_revision(public)
    assert visitor.get("/api/runs/no-such-run/trust").status_code == 404
    for _ in range(access.TRUST_READS_AT_ONCE):
        assert access.trust_reads_building.acquire(blocking=False)
    try:
        assert visitor.get(f"/api/runs/{run_id}/trust").status_code == 503
    finally:
        for _ in range(access.TRUST_READS_AT_ONCE):
            access.trust_reads_building.release()
    assert visitor.get(f"/api/runs/{run_id}/trust").status_code == 200
    assert visitor.get(f"/api/runs/{run_id}/trust").status_code == 429


def test_control_the_owner_store_counts_no_trust_reads(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.address_document_reads, "limit", 1)
    from tests.support import upload_and_ask

    run_id = upload_and_ask(client, "What notice applies?")["run_id"]
    assert [client.get(f"/api/runs/{run_id}/trust").status_code for _ in range(3)] == [200, 200, 200]
