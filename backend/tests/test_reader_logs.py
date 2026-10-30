"""Nothing of a file being read reaches a log line or the API's output (stress test, 2026-10-30, privacy corner).

A visitor's PDF text reached the API's log, where no retention reaches it: the reader's own refusal line printed 200
characters of pypdf's message, which quotes the page stream around a defect ("Invalid Elementary Object starting with
b'}' @61: b' 14 Quokka Lane) Tj }'"), and pypdf's warnings for a file it still reads ("Expecting a NameObject for key but
found 'Tenant Ocelot Ltd'") went, in the reading child, which has no logging set up, through Python's last-resort
handler to the stderr the child shares with the API. The invariant: no character of a file being read reaches a log
line or the API's output; a refusal is logged by kind only. Control: a file read still holds its words.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.ingest import UnsupportedFile, ingest
from tests.test_reader_v16_pdf import line, pdf

BACKEND = Path(__file__).resolve().parents[1]
MARKER = "Tenant Ocelot Ltd 14 Quokka Lane"


def readable_but_warned() -> bytes:
    """A PDF pypdf reads, after logging a repair whose message quotes the file: a string where a page key should be."""
    data = pdf([line(72, 700, "1. Rent") + line(72, 680, "The rent is due monthly.")])
    return data.replace(b"<< /Type /Page ", b"<< /Type /Page (" + MARKER.encode() + b") ", 1)


def refused() -> bytes:
    """A PDF pypdf refuses with a message quoting the page stream around the defect."""
    data = pdf([line(72, 700, "1. Rent") + line(72, 680, "The rent is due monthly.")])
    return data.replace(b"(1. Rent) Tj", b"(" + MARKER.encode() + b") Tj }", 1)


def test_a_refusal_is_logged_by_kind_never_with_the_files_words(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(UnsupportedFile):
        ingest("lease.pdf", refused())
    assert "reader refused" in caplog.text and "PdfReadError" in caplog.text
    assert "Quokka" not in caplog.text and "Ocelot" not in caplog.text


@pytest.mark.parametrize(("make", "outcome"), [(readable_but_warned, "read"), (refused, "refused")])
def test_the_reading_child_writes_nothing_of_the_file_to_the_output_it_shares(tmp_path: Path, make: object, outcome: str) -> None:
    """Through the deployment's own path, a spawned reading child (ingest/bounded.py): the process that asked for the
    reading, standing in for the API, captures every byte its child writes to the shared stdout and stderr."""
    assert callable(make)
    file = tmp_path / "lease.pdf"
    file.write_bytes(make())
    script = tmp_path / "ask.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(BACKEND)!r})
            from app.ingest import bounded

            if __name__ == "__main__":
                try:
                    parsed = bounded.ingest_bounded("lease.pdf", open({str(file)!r}, "rb").read())
                    print("read", len(parsed.sections))
                except Exception as error:
                    print("refused", type(error).__name__)
            """
        ),
        encoding="utf-8",
    )
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180, cwd=tmp_path, check=False)
    assert done.stdout.startswith(outcome), (done.stdout, done.stderr[-2000:])
    assert "Ocelot" not in done.stdout + done.stderr and "Quokka" not in done.stdout + done.stderr, done.stderr[-2000:]


def test_control_the_file_read_still_holds_its_words() -> None:
    assert "The rent is due monthly." in " ".join(s.text for s in ingest("lease.pdf", readable_but_warned()).sections)
