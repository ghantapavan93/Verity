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
