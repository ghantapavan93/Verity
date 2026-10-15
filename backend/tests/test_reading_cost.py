"""What reading a file may cost is bounded where the reading runs (ingest/bounded.py).

An 84 KB .docx of six million empty paragraphs took 848 MB and 35 s to read. A count of elements added for it missed
comments, processing instructions, attributes and text, and made members no part uses inflate. A budget of PDF bytes did
not bound time. (gstack /cso trial and an independent review, 2026-10-13.) So the reading runs in a child process that is
ended past its memory or its time. Each hostile shape below is ended within its bound, a member nothing reads is still
not inflated, and the controls read exactly as they do in this process.
"""

from __future__ import annotations

import io
import multiprocessing
import time
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

from app.ingest import TooLargeToRead, UnsupportedFile, ingest
from app.ingest.bounded import ingest_bounded
from tests.support import CONTRACT
from tests.test_hostile_packages import _base, _rebuild

MB = 1024 * 1024
FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = Path(__file__).resolve().parents[2] / "public" / "samples" / "cloud-service-agreement.docx"


def _in_body(markup: str) -> Callable[[str, bytes], bytes | None]:
    def mutate(name: str, data: bytes) -> bytes | None:
        return data.decode("utf-8").replace("</w:body>", markup + "</w:body>", 1).encode("utf-8") if name == "word/document.xml" else None

    return mutate


def _pdf(contents: list[bytes]) -> bytes:
    """One page per content stream, each its own object."""
    pages = len(contents)
    font = 3 + 2 * pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()]
    for i, content in enumerate(contents):
        packed = zlib.compress(content, 9)
        stream = f"<< /Length {len(packed)} /Filter /FlateDecode >>\nstream\n".encode() + packed + b"\nendstream"
        page = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {4 + 2 * i} 0 R >>"
        objects += [page.encode(), stream]
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


MEMORY_SHAPES: dict[str, Callable[[], str]] = {
    "six million empty paragraphs (the original)": lambda: "<w:p/>" * 6_000_000,
    "comments": lambda: "<!---->" * (60 * MB // 7),
    "processing instructions": lambda: "<?a?>" * (60 * MB // 5),
    "attributes": lambda: ("<w:p " + " ".join(f'a{i}="x"' for i in range(1000)) + "/>") * 6000,
}


@pytest.mark.parametrize("shape", list(MEMORY_SHAPES))
def test_a_reading_past_its_memory_bound_is_ended(shape: str) -> None:
    package = _rebuild(_in_body(MEMORY_SHAPES[shape]()))
    assert len(package) < 1_000_000, "a small upload"
    started = time.perf_counter()
    with pytest.raises(TooLargeToRead, match=r"more than 200 MB of memory"):
        ingest_bounded(f"{shape}.docx", package, memory=200 * MB)
    assert time.perf_counter() - started < 30, shape


def test_a_reading_past_its_time_bound_is_ended() -> None:
    """A 1.6 KB PDF whose one page positions text half a million times read for 20 s in layout mode (2026-10-13)."""
    package = _pdf([b"BT /F1 1 Tf 72 720 Td " + b"0 -1 Td(a)Tj" * (512 * 1024 // 12) + b" ET"])
    assert len(package) < 4_000
    started = time.perf_counter()
    with pytest.raises(TooLargeToRead, match=r"longer than 2 s"):
        ingest_bounded("slow.pdf", package, seconds=2)
    assert time.perf_counter() - started < 10
    assert not multiprocessing.active_children(), "the child was ended, not left reading"


def test_a_member_nothing_reads_is_not_inflated() -> None:
    """A member no part refers to, compressed with bzip2 and declared as 1 byte, was inflated by the element count of
    7b12989 (36 KB file, 862 MB); the reader never opens it, so it costs nothing here, under a bound it would cross."""

    def blob(package: zipfile.ZipFile) -> None:
        member = zipfile.ZipInfo("word/media/blob.bin")
        member.compress_type = zipfile.ZIP_BZIP2
        package.writestr(member, b"\0" * (300 * MB))

    raw = bytearray(_rebuild(lambda _n, _d: None, blob))
    name = b"word/media/blob.bin"
    # Its declared size patched to 1 byte in both headers, as the hostile file had it.
    central = raw.rfind(b"PK\x01\x02", 0, raw.rfind(name))
    raw[central + 24 : central + 28] = (1).to_bytes(4, "little")
    local = raw.find(b"PK\x03\x04")
    while raw[local + 30 : local + 30 + len(name)] != name:
        local = raw.find(b"PK\x03\x04", local + 4)
    raw[local + 22 : local + 26] = (1).to_bytes(4, "little")
    assert len(raw) < 100_000
    parsed = ingest_bounded("unused-member.docx", bytes(raw), memory=200 * MB)
    assert "Effective Date" in " ".join(section.text for section in parsed.sections)


def test_a_member_that_inflates_past_the_package_bound_is_refused_unread() -> None:
    package = _rebuild(lambda _n, _d: None, lambda zipped: zipped.writestr("word/media/image1.png", b"\0" * (70 * MB)))
    assert len(package) < 1_000_000
    with pytest.raises(TooLargeToRead, match=r"unpacks to 70 MB; the limit is 64 MB"):
        ingest_bounded("blob.docx", package)


@pytest.mark.parametrize("fixture", [SAMPLE, FIXTURES / "services-agreement.pdf"])
def test_the_child_reads_exactly_what_this_process_reads(fixture: Path) -> None:
    """Control: within its bounds the child changes nothing about a reading."""
    data = fixture.read_bytes()
    assert ingest_bounded(fixture.name, data) == ingest(fixture.name, data)


def test_a_long_contract_reads_within_the_bounds() -> None:
    """Control: 6,000 paragraphs of real text, well past any contract measured (the largest of 323: 204,093 elements)."""
    document = DocxDocument()
    for number in range(1, 3001):
        document.add_paragraph(f"{number}. Obligation {number}")
        document.add_paragraph(f"The Provider shall perform obligation {number} within thirty (30) days of written notice.")
    buffer = io.BytesIO()
    document.save(buffer)
    text = " ".join(section.text for section in ingest_bounded("long.docx", buffer.getvalue()).sections)
    assert "obligation 1 within" in text and "obligation 3000 within" in text


def test_a_reader_refusal_comes_back_as_it_was_raised() -> None:
    """A damaged file is refused by the reader in the child, with the reader's reason, not as a resource refusal."""
    with pytest.raises(UnsupportedFile, match=r"not a readable \.docx package") as refused:
        ingest_bounded("damaged.docx", _base()[:100])
    assert refused.type is UnsupportedFile


def test_an_upload_is_read_in_the_child_where_the_application_runs(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The upload route reads through the child (bounded.READ_IN_CHILD, on wherever the application runs): a file past the
    memory bound is refused with 413 and the reason, and nothing is stored."""
    from app.ingest import bounded

    monkeypatch.setattr(bounded, "READ_IN_CHILD", True)
    monkeypatch.setattr(bounded, "READ_MEMORY_BYTES", 200 * MB)
    refused = client.post("/api/documents", files={"file": ("comments.docx", _rebuild(_in_body(MEMORY_SHAPES["comments"]())), "application/octet-stream")})
    assert refused.status_code == 413 and "more than 200 MB of memory" in refused.json()["detail"]
    assert client.get("/api/documents").json() == []
    # Control: an ordinary contract goes through the same child and is stored.
    assert client.post("/api/documents", files={"file": (SAMPLE.name, SAMPLE.read_bytes(), "application/octet-stream")}).status_code == 201


# ---------------------------------------------------------------------------- round 3 (counter-review of round 2)


def test_any_other_failure_in_the_child_is_a_server_error_not_a_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A bug in a reader is a 500 in the API's process; in the child it came back as a 413 "past its bounds"."""
    from app.ingest import bounded

    def broken(_name: str, _data: bytes) -> None:
        raise ValueError("a reader bug")

    monkeypatch.setattr(bounded, "ingest", broken)
    handed = tmp_path / "handed"
    handed.write_bytes(len(b"x.txt").to_bytes(4, "big") + b"x.txt" + b"x")  # as ingest_bounded hands a file over: its name, then it
    receive, send = multiprocessing.Pipe(duplex=False)
    bounded._read_in_child(str(handed), send)  # type: ignore[arg-type, unused-ignore]  # PipeConnection on Windows
    kind, value = receive.recv()
    assert (kind, value) == ("error", "ValueError: a reader bug")
    with pytest.raises(RuntimeError, match="a reader bug"):
        bounded._outcome(kind, value)
    with pytest.raises(TooLargeToRead):
        bounded._outcome("too_large", "past a bound")


def test_no_more_than_two_readings_run_at_once_whoever_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The slots are in the one function every reading goes through: a document read again for a revision check went
    around them (counter-review, 2026-10-13)."""
    import threading

    from app.ingest import bounded

    inside, peak, lock = 0, 0, threading.Lock()

    def slow(name: str, data: bytes) -> object:
        nonlocal inside, peak
        with lock:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.2)
        with lock:
            inside -= 1
        return name

    monkeypatch.setattr(bounded, "ingest", slow)
    readers = [threading.Thread(target=bounded.read_file, args=(f"c{i}.txt", b"x")) for i in range(6)]
    for reader in readers:
        reader.start()
    for reader in readers:
        reader.join()
    assert peak == bounded.READINGS_AT_ONCE


def test_a_reading_refused_at_a_bound_is_not_remembered_as_unreadable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A re-read timed out under load stayed "unreadable" for the life of the process (counter-review, 2026-10-13)."""
    from app.application import trust_run

    stored = tmp_path / "stored.txt"
    stored.write_bytes(CONTRACT.encode())
    attempts: list[int] = []

    def once_too_slow(name: str, data: bytes) -> object:
        attempts.append(1)
        if len(attempts) == 1:
            raise TooLargeToRead("reading the file took longer than 30 s; no contract needs that long")
        return ingest(name, data)

    monkeypatch.setattr(trust_run, "read_file", once_too_slow)
    trust_run.forget_readings()
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is None
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None, "asked again, it is read"


def test_the_child_is_started_with_a_path_never_the_file_or_its_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The file went to the child through the pipe that starts it: on Windows a child that died before reading 2 MB of it
    left the parent blocked in start() past every deadline (war room W5 p10). The start carries a path and the answer
    pipe, the same size whatever the file and its name; the name travels in the file, and the file is removed after."""
    from app.ingest import bounded

    real = bounded._process_context()
    handed: list[tuple[object, ...]] = []

    class Recording:
        def Pipe(self, duplex: bool) -> object:
            return real.Pipe(duplex=duplex)

        def Process(self, target: object, args: tuple[object, ...], daemon: bool) -> object:
            handed.append(args)
            return real.Process(target=target, args=args, daemon=daemon)  # type: ignore[arg-type]

    monkeypatch.setattr(bounded, "_process_context", Recording)
    long_name = "a contract named at length " * 200 + ".txt"
    assert bounded.ingest_bounded(long_name, CONTRACT.encode()) == ingest(long_name, CONTRACT.encode())
    ((path, _answer),) = handed
    assert isinstance(path, str) and len(path) < 300, handed
    assert not Path(path).exists(), "the file handed over is removed once read"


@pytest.mark.parametrize("dies", ["while starting", "before answering"])
def test_a_child_that_ends_without_an_answer_is_noticed_when_it_ends(dies: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows a child that died while starting was noticed only at the deadline with a 1 KB file, and never with a
    2 MB one: the parent stayed blocked in start() (war room W5 p10). The parent now waits on the child's end as well as
    on its answer, and the start carries no file."""
    import threading

    from app.ingest import bounded
    from tests import dying_child

    target = dying_child.ExitWhileStarting() if dies == "while starting" else dying_child.exit_at_once
    monkeypatch.setattr(bounded, "_read_in_child", target)
    for size in (1024, 2 * 1024 * 1024):
        outcome: dict[str, str] = {}

        def run(size: int = size, outcome: dict[str, str] = outcome) -> None:
            try:
                bounded.ingest_bounded("contract.txt", b"x" * size, seconds=20)
            except TooLargeToRead as refused:
                outcome["refused"] = str(refused)
            except Exception as other:  # noqa: BLE001 - reported below as what it was
                outcome["other"] = f"{type(other).__name__}: {other}"

        started = time.perf_counter()
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(15)
        took = time.perf_counter() - started
        assert "refused" in outcome and took < 10, (size, outcome, took)
        assert "no contract causes" in outcome["refused"]


def test_a_document_asked_for_by_many_at_once_is_read_once_and_no_request_waits_long(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sixty requests at once for documents read by an earlier reader each read on a thread of the pool every sync route
    shares, waiting for a slot, and /api/health answered after 21.5 s (war room W5 p5). The same document is read once,
    off the requests' threads; each request waits REREAD_WAIT_SECONDS at most, and the reading is there for the next."""
    import threading

    from app.application import trust_run

    stored = tmp_path / "stored.txt"
    stored.write_bytes(CONTRACT.encode())
    reads: list[int] = []

    def slow(name: str, data: bytes, **_kwargs: object) -> object:
        reads.append(1)
        time.sleep(1.0)
        return ingest(name, data)

    monkeypatch.setattr(trust_run, "read_file", slow)
    monkeypatch.setattr(trust_run, "REREAD_WAIT_SECONDS", 0.2)
    trust_run.forget_readings()
    took: list[float] = []
    answers: list[object] = []

    def ask() -> None:
        began = time.perf_counter()
        answers.append(trust_run._read_again(stored, "stored.txt", "test-reader"))
        took.append(time.perf_counter() - began)

    askers = [threading.Thread(target=ask) for _ in range(20)]
    for asker in askers:
        asker.start()
    for asker in askers:
        asker.join()
    assert (len(reads), max(took) < 0.8, answers) == (1, True, [None] * 20), (len(reads), max(took))
    time.sleep(1.2)
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None, "the reading finished for the next request"
    assert len(reads) == 1


def test_documents_read_again_take_one_reading_slot_at_a_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Readings again went around the per-network turn and could hold both slots uploads need; one runs at a time."""
    import threading

    from app.application import trust_run

    inside, peak, lock = 0, 0, threading.Lock()

    def slow(name: str, data: bytes, **_kwargs: object) -> object:
        nonlocal inside, peak
        with lock:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.15)
        with lock:
            inside -= 1
        return ingest(name, data)

    monkeypatch.setattr(trust_run, "read_file", slow)
    trust_run.forget_readings()
    paths = []
    for index in range(6):
        path = tmp_path / f"d{index}.txt"
        path.write_bytes(f"{CONTRACT}\nCopy {index}.".encode())
        paths.append(path)
    askers = [threading.Thread(target=trust_run._read_again, args=(path, path.name, "test-reader")) for path in paths]
    for asker in askers:
        asker.start()
    for asker in askers:
        asker.join()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not all(path.name and trust_run._read_again(path, path.name, "test-reader") for path in paths):
        time.sleep(0.1)
    assert peak == 1


def test_a_start_removes_the_reading_files_a_stopped_process_left_and_readings_hand_over_there(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Readings handed their files over in the system's temporary folder, which nothing empties on Windows: a
    force-stopped API left contracts there, outside retention (Codex review, round 3). They now hand over in the store's
    own folder, which the API empties at start."""
    from app.ingest import bounded

    monkeypatch.setattr(bounded, "HANDOFF_DIR", None)  # restored after the test
    folder = tmp_path / "reading"
    folder.mkdir(mode=0o700)  # this user's alone, as use_handoff_dir requires on Linux
    (folder / f"{bounded.HANDOFF_PREFIX}left-by-a-kill").write_bytes(b"a contract")
    (folder / "not-a-reading.txt").write_bytes(b"control")
    assert bounded.use_handoff_dir(folder) == 1
    assert sorted(path.name for path in folder.iterdir()) == ["not-a-reading.txt"]
    real = bounded._process_context()
    handed: list[tuple[object, ...]] = []

    class Recording:
        def Pipe(self, duplex: bool) -> object:
            return real.Pipe(duplex=duplex)

        def Process(self, target: object, args: tuple[object, ...], daemon: bool) -> object:
            handed.append(args)
            return real.Process(target=target, args=args, daemon=daemon)  # type: ignore[arg-type]

    monkeypatch.setattr(bounded, "_process_context", Recording)
    assert bounded.ingest_bounded("contract.txt", CONTRACT.encode()).sections
    ((path, _answer),) = handed
    assert Path(str(path)).parent == folder and not Path(str(path)).exists()
