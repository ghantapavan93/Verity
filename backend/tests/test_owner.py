"""A stage row's owner is a process; a run whose owner provably died can be recovered at once, and nothing else can."""

from __future__ import annotations

import os
import subprocess
import sys

from app.runs.owner import ProcessIdentity, owner_is_alive_here, owner_is_gone, start_token_of, this_process


def test_this_process_identifies_itself_and_is_never_gone() -> None:
    me = this_process()
    assert me.pid == os.getpid() and me.host
    assert ProcessIdentity.parse(me.render()) == me
    assert not owner_is_gone(me.render())


def test_unknown_owners_other_hosts_and_garbage_are_never_declared_gone() -> None:
    assert not owner_is_gone(None) and not owner_is_gone("")
    assert not owner_is_gone("some-other-host:1:")
    assert not owner_is_gone("not an identity")
    assert not owner_is_gone(f"{this_process().host}:notapid:")


def test_a_process_that_has_exited_is_gone_and_a_live_one_is_not() -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        live = ProcessIdentity(this_process().host, child.pid, "")
        assert not owner_is_gone(live.render())
    finally:
        child.kill()
        child.wait()
    assert owner_is_gone(ProcessIdentity(this_process().host, child.pid, "").render()), "the pid no longer exists"


def test_a_pid_reused_by_a_later_process_is_gone_when_the_start_token_differs() -> None:
    me = this_process()
    if not me.started:
        return  # the platform gives no start token; pid liveness alone applies
    reused = ProcessIdentity(me.host, os.getppid() if os.getppid() != me.pid else me.pid, "1")
    if reused.pid == me.pid:
        return
    # The parent is alive with its own start token, which is not "1": the row was written by an earlier process with that pid.
    assert owner_is_gone(reused.render())


def test_an_earlier_process_with_this_pid_is_gone_and_not_this_one() -> None:
    """In a container the API is pid 1 under the same hostname after every restart. A stage opened by the previous pid 1
    was taken for this process's own live work, so a run interrupted by the restart stayed in progress for good and every
    identical question was handed it (cloud rehearsal, 2026-10-09). The start token tells the two apart."""
    me = this_process()
    if not me.started:
        return  # the platform gives no start token; pid liveness alone applies
    earlier = ProcessIdentity(me.host, me.pid, "1")
    assert owner_is_gone(earlier.render())
    assert not owner_is_alive_here(earlier.render())
    assert owner_is_alive_here(me.render()) and not owner_is_gone(me.render()), "this process itself is alive and here"


def test_a_start_after_a_reboot_never_matches_one_before_it() -> None:
    """Linux counts a process's start in clock ticks since boot, and after a reboot a container's pid 1 starts at
    about the same uptime: the same pid and the same tick count would pass for the process that died before the
    reboot, and its interrupted run would never be recovered. The boot is part of the token."""
    before, after = start_token_of("1866531", "boot-a"), start_token_of("1866531", "boot-b")
    assert before != after
    assert start_token_of("1866531", None) == "1866531", "where the boot cannot be read, the tick count alone"
