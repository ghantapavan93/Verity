"""After a retention pass, the API process keeps nothing of an ended visitor that it can reach, and no address past its
window (stress test, 2026-10-30, privacy 2).

Disk and log were clean after a purge, but the process still held a deleted visitor's defined terms (links._use_of,
re's caches) and 40 characters of contract prose (the revision check's search, in re's caches), and the hourly windows
kept every address and /64 they had counted until 4,096 keys were held: at demo traffic, for the life of the process,
the only place it kept a visitor's address. Every retention pass now forgets what the process derived from documents
(application/retention.forget_process_state) and every window drops what is past its window (access.prune_windows).
This makes the residue unreachable, not erased: freed memory is not zeroed, and only a restart drops it.
"""

from __future__ import annotations

import re

from app.api import access
from app.api.access import SlidingWindow
from app.application import clause_location, retention, start_run, trust_run
from app.runs import links


def test_a_key_past_its_window_is_dropped_at_the_next_pass() -> None:
    window = SlidingWindow(30, 3600)
    assert window.take("198.51.100.7", now=0.0) is None
    assert window.take("198.51.100.8", now=3000.0) is None
    window.prune(now=3700.0)
    assert set(window._events) == {"198.51.100.8"}, "the day-0 address is gone; one inside its window is kept"


def test_a_window_drops_stale_keys_on_its_own_once_a_window_has_passed() -> None:
    window = SlidingWindow(30, 3600)
    window.take("2001:db8:1:2::/64", now=0.0)
    for day in range(1, 31):  # 100 new keys a day for a month, never reaching 4,096
        for n in range(100):
            window.take(f"203.0.{day}.{n}", now=day * 86400.0)
    assert "2001:db8:1:2::/64" not in window._events
    assert len(window._events) <= 100


def test_every_window_is_pruned_by_the_pass() -> None:
    windows = [access.visits, access.address_uploads, access.address_runs, access.workspace_writes, access.address_writes]
    for window in windows:
        window.reset()
        window.take("198.51.100.9", now=0.0)
    access.prune_windows(now=10**7)
    assert all(not window._events for window in windows)


def test_the_pass_forgets_what_the_process_derived_from_documents() -> None:
    links._use_of("Quillfernwhistle Partners")
    re.compile(r"Vexmorrowdale\ fees")
    with clause_location._clause_numbers_lock:
        clause_location._clause_numbers[("a reading",)] = frozenset({"1"})
    with start_run._STARTS_LOCK:
        start_run._STARTS[("document", "sha")] = ("the Amendment Date",)
    retention.forget_process_state()
    assert links._use_of.cache_info().currsize == 0
    assert not clause_location._clause_numbers and not start_run._STARTS
    assert not trust_run._readings
    assert "Vexmorrowdale" not in " ".join(str(key) for key in re._cache)  # type: ignore[attr-defined]
