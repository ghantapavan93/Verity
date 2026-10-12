"""The API container's health check, which also restarts a server that is running but no longer answering.

Docker marks a container whose health check fails as unhealthy and does nothing else; its restart policy acts only when
the process exits. On the workstation an API that stayed up but stopped answering left the public site at 502 for 33
minutes, until deploy/supervise.ps1 learned to probe it and stop it. This is the same rule, in the container: a server
that has run past its first minute and fails three probes in a row (about ninety seconds) is killed, the container exits,
and `restart: unless-stopped` starts a new one, which fails the runs the old one left in flight (app/runs/owner.py).

It needs `init: true` in compose.yml: the server must not be pid 1, which ignores a kill sent from inside its container.
Misses are counted in /tmp, which is the container's own and empty again after every restart.
"""

from __future__ import annotations

import os
import signal
import sys
import time
import urllib.request

PROBE = "http://127.0.0.1:8000/api/health"
MISSES_FILE = "/tmp/verity-liveness-misses"
MISSES = 3  # deploy/supervise.ps1 HEALTH_MISSES
GRACE_SECONDS = 60  # deploy/supervise.ps1 HEALTH_GRACE_SECONDS: a server starting up is not judged


def answering() -> bool:
    try:
        with urllib.request.urlopen(PROBE, timeout=5) as response:
            return bool(response.status == 200)
    except Exception:
        return False


def server() -> tuple[int, float] | None:
    """The uvicorn process serving the API and its age in seconds, or None when there is none."""
    ticks = os.sysconf("SC_CLK_TCK")
    with open("/proc/uptime") as uptime:
        now = float(uptime.read().split()[0])
    for entry in os.listdir("/proc"):
        # Pid 1 is docker-init, whose own command line names the server it runs; and no signal sent from inside the
        # container can end pid 1 anyway (rehearsal, 2026-10-12: the first version chose it and the kill did nothing).
        if not entry.isdigit() or int(entry) in (1, os.getpid()):
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as cmdline:
                argv = cmdline.read().split(b"\0")
            with open(f"/proc/{entry}/stat") as stat:
                started = int(stat.read().rsplit(")", 1)[1].split()[19]) / ticks
        except (OSError, IndexError, ValueError):
            continue
        if b"uvicorn" in b" ".join(argv) and b"app.main:app" in argv:
            return int(entry), now - started
    return None


def misses(value: int | None = None) -> int:
    if value is not None:
        with open(MISSES_FILE, "w") as file:
            file.write(str(value))
        return value
    try:
        with open(MISSES_FILE) as file:
            return int(file.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def main() -> int:
    if answering():
        misses(0)
        return 0
    found = server()
    if found is None or found[1] < GRACE_SECONDS:
        return 1  # nothing to judge yet: Docker reports the state, the restart policy handles an exit
    count = misses(misses() + 1)
    print(f"api pid {found[0]} did not answer {PROBE} ({count} of {MISSES})", file=sys.stderr)
    if count >= MISSES:
        print(f"api pid {found[0]} is running but not answering: killing it so the container restarts", file=sys.stderr)
        misses(0)
        os.kill(found[0], signal.SIGKILL)
        time.sleep(1)
    return 1


if __name__ == "__main__":
    sys.exit(main())
