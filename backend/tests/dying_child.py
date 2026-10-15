"""Reading children that end with no answer (tests/test_reading_cost.py), in a module of their own so that a child process
can import them by name."""

from __future__ import annotations

import os


def exit_at_once(*_args: object) -> None:
    """Started, then ended before answering: a reader the kernel killed."""
    os._exit(3)


class ExitWhileStarting:
    """A target the child dies on while it is still being started: unpickling it ends the process, before the child has
    read the rest of what started it or taken its end of the answer pipe (low memory, an import error)."""

    def __reduce__(self) -> tuple[object, tuple[int]]:
        return (os._exit, (3,))
