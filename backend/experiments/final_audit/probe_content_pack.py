"""Phases 13, 17, 18: hostile content end to end, the evidence pack under size and tampering, and file/database
failures injected at the write."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import tracemalloc
import zipfile

from harness import CONTRACT, QUOTE, Report, ScriptedProvider, Store

ONLY = set(sys.argv[1:])


def unpack(data: bytes) -> pathlib.Path:
    folder = pathlib.Path(tempfile.mkdtemp(prefix="verity-pack-"))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(folder)
    return folder


def verify(folder: pathlib.Path) -> tuple[int, str]:
    out = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return out.returncode, (out.stdout + out.stderr)


# ------------------------------------------------------------------------------------------- Phase 13
if not ONLY or "13" in ONLY:
    r = Report("Phase 13 - content injection and Unicode")
    SCRIPT = "<script>alert('x')</script>"
    IMG = "<img src=x onerror=alert(1)>"
    hostile_clause = (
        f"Either party {IMG} may terminate &lt;b&gt;this&lt;/b&gt; Agreement \u202eesrever\u202c with zero\u200bwidth and emoji 😀 and astral 𝒜𝒷𝒸 "
        "and combining e\u0301 upon sixty (60) days' written notice to the other party."
    )
    text = (
        f"SERVICES AGREEMENT\n\n1. {SCRIPT} Term\n\nThis Agreement lasts twelve (12) months. {'W' * 5000}\n\n"
        f"2. Termination for Convenience\n\n{hostile_clause}\n\n3. Governing Law\n\nDelaware law governs.\n"
    )
    provider = ScriptedProvider()
    s = Store(provider=provider)
    doc = s.upload(text, name=f"{IMG}.txt")
    r.note("stored document name", "INFO", repr(doc["name"]))
    gid = s.guidance(f"We require at least 90 days' written notice for termination for convenience. {SCRIPT} {IMG}")
    provider.payload = {
        "findings": [
            {
                "topic": f"Termination {SCRIPT}",
                "conclusion": f"Sixty days {IMG} &amp; more \u202e reversed",
                "status_hint": "pass",
                "evidence": [{"section_id": "sec_1", "quote": hostile_clause}],
                "guidance_reference": f"at least 90 days {SCRIPT}",
                "observed": "60 days' written notice",
                "required": "at least 90 days",
                "suggested_position": f"90 days {IMG}",
            }
        ],
        "insufficient_evidence": False,
        "note": None,
    }
    run = s.wait(s.ask(doc["id"], f"On what notice may a party terminate? {SCRIPT} 😀", gid).json()["id"])
    r.check("the run completes on hostile content", run["stage"] == "complete", f"{run['stage']} {run.get('error') or ''}")
    if run["stage"] == "complete":
        finding = run["findings"][0]
        span = finding["spans"][0]
        document = s.client.get(f"/api/documents/{doc['id']}").json()
        section = next(x for x in document["sections"] if x["id"] == span["sectionId"])
        r.check(
            "the span's offsets recover the quote exactly, astral and combining characters included",
            section["text"][span["start"] : span["end"]] == hostile_clause,
            span["method"],
        )
        r.check(
            "code still decides from the quote",
            finding["status"] == "needs_review" and finding["statusSource"] == "computed_days",
            f"{finding['status']} / {finding['statusSource']}",
        )
        r.check("the API returns the hostile strings as data, unaltered", SCRIPT in finding["topic"] and IMG in finding["conclusion"])
        s.client.post(f"/api/findings/{finding['id']}/review", json={"verdict": "confirmed", "reviewer": "<b>Eve</b> \u202e", "note": f"note {SCRIPT} {IMG}"})
        memo = s.client.post("/api/memos", json={"runId": run["id"]})
        r.check("the memo is written", memo.status_code == 201, f"HTTP {memo.status_code} {memo.text[:120] if memo.status_code != 201 else ''}")
        if memo.status_code == 201:
            html = s.client.get(memo.json()["htmlUrl"]).text
            tags = re.findall(r"<(script|img|iframe|svg|object|embed)\b", html, re.I)
            handlers = re.findall(r"<[^>]*\bon\w+\s*=", html, re.I)
            r.check(
                "memo HTML carries no script, img or event-handler markup from any input", not tags and not handlers, f"tags {tags[:3]} handlers {handlers[:2]}"
            )
            r.check("the hostile text is present, escaped", "&lt;script&gt;" in html and "&lt;img" in html)
            docx = s.client.get(memo.json()["docxUrl"])
            from docx import Document as Docx

            try:
                word = Docx(io.BytesIO(docx.content))
                body = "\n".join(p.text for p in word.paragraphs) + "\n".join(c.text for t in word.tables for row in t.rows for c in row.cells)
                r.check("the DOCX opens and carries the text as text", SCRIPT in body and "😀" in body, f"{len(body)} chars")
            except Exception as error:  # noqa: BLE001 - a probe: report what happened
                r.check("the DOCX opens", False, repr(error)[:200])
        pack = s.client.get(f"/api/runs/{run['id']}/evidence-pack")
        names = zipfile.ZipFile(io.BytesIO(pack.content)).namelist()
        unsafe = [n for n in names if n.startswith(("/", "\\")) or ".." in n or ":" in n or "\\" in n]
        r.check("pack member names are safe paths", not unsafe, f"{names}")
        folder = unpack(pack.content)
        code, out = verify(folder)
        r.check("the pack for the hostile run verifies itself", code == 0, out.strip().splitlines()[-1] if out.strip() else "")
        disposition = pack.headers.get("content-disposition", "")
        r.note("pack Content-Disposition", "INFO", disposition)
    r.done()

# ------------------------------------------------------------------------------------------- Phase 17
if not ONLY or "17" in ONLY:
    r = Report("Phase 17 - evidence pack")
    big = "MASTER AGREEMENT\n\n" + "\n\n".join(
        f"{i}. Clause {i}\n\n" + ("This clause states an obligation of the parties in ordinary words. " * 30) for i in range(1, 1501) if i != 700
    )
    big = (
        big.replace("699. Clause 699", "699. Clause 699\n\n" + "x")
        + f"\n\n2000. Termination for Convenience\n\n{QUOTE} On termination, Customer pays all Fees accrued.\n"
    )
    s = Store()
    t0 = time.perf_counter()
    doc = s.upload(big, name="large.txt")
    upload_s = time.perf_counter() - t0
    r.note(
        "large document",
        "INFO",
        f"{len(big.encode()) / 1e6:.1f} MB, {len(s.client.get('/api/documents/' + doc['id']).json()['sections'])} sections, read in {upload_s:.1f} s",
    )
    gid = s.guidance()
    run = s.wait(s.ask(doc["id"], "May either party terminate for convenience, and on what notice?", gid).json()["id"], timeout_s=120)
    r.check("a run on the large document completes", run["stage"] == "complete", f"{run['stage']} {run.get('error') or ''}")
    tracemalloc.start()
    t0 = time.perf_counter()
    pack = s.client.get(f"/api/runs/{run['id']}/evidence-pack")
    build_s = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    r.note(
        "pack for the large run",
        "INFO",
        f"HTTP {pack.status_code}, {len(pack.content) / 1e6:.2f} MB zip, built in {build_s:.2f} s, peak traced memory {peak / 1e6:.0f} MB",
    )
    folder = unpack(pack.content)
    code, out = verify(folder)
    r.check("clean pack: verify.py exits 0", code == 0, out.strip().splitlines()[-1] if out.strip() else "")
    leaks = []
    for member in folder.rglob("*"):
        if member.is_file():
            blob = member.read_bytes()
            for needle in (b"C:\\\\Users", b"C:\\Users", b"AppData", str(s.dir).encode(), os.environ.get("USERNAME", "user-name").split()[0].encode()):
                if needle in blob:
                    leaks.append((member.name, needle.decode(errors="replace")))
    r.check("no machine path or user name inside the pack", not leaks, str(leaks[:4]))
    record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    r.note("run.json verifier block", "INFO", json.dumps(record["verifier"])[:200])

    def tampered(change) -> tuple[int, str]:  # type: ignore[no-untyped-def]
        copy = unpack(pack.content)
        change(copy)
        code, out = verify(copy)
        failing = [line for line in out.splitlines() if "FAIL" in line]
        return code, (failing[0] if failing else out.strip().splitlines()[-1] if out.strip() else "")

    def edit_document(folder: pathlib.Path) -> None:
        target = next((folder / "document").iterdir())
        target.write_bytes(target.read_bytes().replace(b"sixty (60)", b"ninety (90)"))

    def edit_sections(folder: pathlib.Path) -> None:
        p = folder / "sections.json"
        p.write_text(p.read_text(encoding="utf-8").replace("sixty (60) days", "ninety (90) days"), encoding="utf-8")

    def edit_quote(folder: pathlib.Path) -> None:
        p = folder / "findings.json"
        p.write_text(p.read_text(encoding="utf-8").replace("sixty (60) days", "ninety (90) days"), encoding="utf-8")

    def edit_offsets(folder: pathlib.Path) -> None:
        p = folder / "findings.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data[0]["spans"][0]["start"] += 7
        p.write_text(json.dumps(data), encoding="utf-8")

    def edit_status(folder: pathlib.Path) -> None:
        p = folder / "findings.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data[0]["status"] = "pass"
        p.write_text(json.dumps(data), encoding="utf-8")

    def edit_question(folder: pathlib.Path) -> None:
        p = folder / "run.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["question"] = "A different question"
        p.write_text(json.dumps(data), encoding="utf-8")

    def edit_model_input(folder: pathlib.Path) -> None:
        p = folder / "model_input" / "user.txt"
        p.write_text(p.read_text(encoding="utf-8").replace("sixty (60)", "ninety (90)"), encoding="utf-8")

    def edit_guidance(folder: pathlib.Path) -> None:
        p = folder / "guidance.txt"
        p.write_text(p.read_text(encoding="utf-8").replace("90", "30"), encoding="utf-8")

    for name, change, must_fail in [
        ("the document bytes are edited", edit_document, True),
        ("sections.json is edited", edit_sections, True),
        ("a quote in findings.json is edited", edit_quote, True),
        ("a span's offsets are moved", edit_offsets, True),
        ("the model input file is edited", edit_model_input, True),
        ("the guidance file is edited", edit_guidance, True),
        ("a finding's status is flipped to pass", edit_status, None),
        ("the question in run.json is edited", edit_question, None),
    ]:
        code, line = tampered(change)
        if must_fail:
            r.check(f"tampered: {name} -> verify fails", code != 0, line[:150])
        else:
            r.note(
                f"tampered: {name}", "INFO", f"verify exit {code}: {line[:150]}  (not bound by a hash in the pack: {'detected' if code else 'NOT detected'})"
            )
    r.done()

# ------------------------------------------------------------------------------------------- Phase 18
if not ONLY or "18" in ONLY:
    r = Report("Phase 18 - file and database failures at the write")
    s = Store()
    real_write = pathlib.Path.write_bytes
    armed = {"on": True}

    def failing_write(self: pathlib.Path, data: bytes) -> int:
        if armed["on"] and "documents" in self.parts:
            armed["on"] = False
            raise OSError("injected: no space left on device")
        return real_write(self, data)

    pathlib.Path.write_bytes = failing_write  # type: ignore[method-assign]
    first = s.client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode(), "text/plain")})
    pathlib.Path.write_bytes = real_write  # type: ignore[method-assign]
    rows = sqlite3.connect(s.db_path).execute("select id, sha256, name from documents").fetchall()
    r.note("upload with the bytes' write failing", "INFO", f"HTTP {first.status_code}; document rows afterwards: {len(rows)}")
    second = s.client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode(), "text/plain")})
    stored = list((s.dir / "documents").glob("*")) if (s.dir / "documents").exists() else []
    sha = hashlib.sha256(CONTRACT.encode()).hexdigest()
    r.check(
        "after the retry the document row has its original bytes on disk",
        second.status_code in (200, 201) and any(p.name.startswith(sha) for p in stored),
        f"retry HTTP {second.status_code}; files {[p.name[:12] for p in stored]}",
    )
    if second.status_code in (200, 201):
        gid = s.guidance()
        run = s.wait(s.ask(second.json()["id"], "On what notice may a party terminate for convenience?", gid).json()["id"])
        pack = s.client.get(f"/api/runs/{run['id']}/evidence-pack")
        names = zipfile.ZipFile(io.BytesIO(pack.content)).namelist() if pack.status_code == 200 else []
        r.check("the run's evidence pack carries the original document", any(n.startswith("document/") for n in names), str(names))

    # A database write that fails while findings are being stored: the run must end as an honest failure.
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from app.models import Finding

    s2 = Store()
    doc = s2.upload()
    gid = s2.guidance()
    real_commit = Session.commit
    armed2 = {"on": True}

    def failing_commit(self: Session) -> None:
        if armed2["on"] and any(isinstance(row, Finding) for row in self.new):
            armed2["on"] = False
            raise OperationalError("INSERT INTO findings", {}, Exception("injected: database is locked"))
        real_commit(self)

    Session.commit = failing_commit  # type: ignore[method-assign]
    run = s2.wait(s2.ask(doc["id"], "On what notice may a party terminate for convenience?", gid).json()["id"])
    Session.commit = real_commit  # type: ignore[method-assign]
    r.check(
        "a failed findings write ends the run as failed, not complete",
        run["stage"] == "failed" and not run["findings"],
        f"{run['stage']} · {run.get('error', '')[:80]}",
    )
    con = sqlite3.connect(s2.db_path)
    orphans = con.execute("select count(*) from findings where run_id = ?", (run["id"],)).fetchone()[0]
    r.check("no finding row of the failed run was kept", orphans == 0, f"{orphans} rows")
    again = s2.wait(s2.ask(doc["id"], "On what notice may a party terminate for convenience?", gid).json()["id"])
    r.check("the same question can be asked again and completes", again["id"] != run["id"] and again["stage"] == "complete", again["stage"])

    # The pack is built in memory and never stored: a failure while building it must persist nothing.
    import app.application.evidence_pack as pack_module

    real_zip = zipfile.ZipFile.writestr
    armed3 = {"on": True}

    def failing_writestr(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if armed3["on"]:
            armed3["on"] = False
            raise OSError("injected: write failed")
        return real_zip(self, *args, **kwargs)

    zipfile.ZipFile.writestr = failing_writestr  # type: ignore[method-assign]
    broken = s2.client.get(f"/api/runs/{again['id']}/evidence-pack")
    zipfile.ZipFile.writestr = real_zip  # type: ignore[method-assign]
    fine = s2.client.get(f"/api/runs/{again['id']}/evidence-pack")
    r.check(
        "a pack that fails to build is a 500 and the next request is whole",
        broken.status_code == 500 and fine.status_code == 200 and fine.content[:2] == b"PK",
        f"{broken.status_code} then {fine.status_code}",
    )
    _ = pack_module
    r.done()
