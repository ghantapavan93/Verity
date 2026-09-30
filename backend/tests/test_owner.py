"""A stage row's owner is a process; a run whose owner provably died can be recovered at once, and nothing else can."""

from __future__ import annotations

import os
import subprocess
import sys

from app.runs.owner import ProcessIdentity, owner_is_gone, this_process


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
