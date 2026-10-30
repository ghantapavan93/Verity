"""Build the fixture behind docs/DEMO-PROOF.md: one CUAD v1 contract, outside every measured set, as a plain DOCX.

The text is the contract's public text exactly as CUAD ships it (The Atticus Project, CC BY 4.0, the archive
recorded in backend/data/cuad/SOURCE.txt), one paragraph per non-empty line, written with python-docx's default
template. No heading styles, headers, footers, fields or tables are added, so the reading has nothing to omit
and nothing is staged. The contract is named here; it is not in CUAD-30, not in the SkillOpt set, and not the
golden document, and the workbench had never read it before the proof.

    cd backend && .venv/Scripts/python experiments/demo_proof/make_fixture.py <out.docx>
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

from docx import Document

TITLE = "MTITECHNOLOGYCORP_11_16_2004-EX-10.102-Reseller Agreement Premier Addendum"
# python-docx stamps every zip member with the wall clock, so two builds of the same text differ only in those
# timestamps; pinning them makes the package hash a function of the text alone.
PINNED_TIME = (1980, 1, 1, 0, 0, 0)


def pin_member_times(path: Path) -> None:
    """Rewrite the package with every member at the pinned time; the members' bytes are untouched."""
    with zipfile.ZipFile(path) as source:
        members = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for info, data in members:
            pinned = zipfile.ZipInfo(info.filename, date_time=PINNED_TIME)
            pinned.compress_type = zipfile.ZIP_DEFLATED
            pinned.external_attr = info.external_attr
            target.writestr(pinned, data)


def main(out: Path) -> None:
    backend = Path(__file__).resolve().parents[2]
    archive = zipfile.ZipFile(backend / "data" / "cuad" / "data.zip")
    name = next(member for member in archive.namelist() if member.endswith("CUADv1.json"))
    contracts = json.loads(archive.read(name))["data"]
    contract = next(c for c in contracts if c["title"] == TITLE)
    text = contract["paragraphs"][0]["context"]

    document = Document()
    paragraphs = 0
    for line in text.splitlines():
        if line.strip():
            document.add_paragraph(line.strip())
            paragraphs += 1
    document.save(str(out))
    pin_member_times(out)
    data = out.read_bytes()
    print(f"{out}: {len(data)} bytes, {paragraphs} paragraphs from {len(text)} characters, sha256 {hashlib.sha256(data).hexdigest()}")
    expert = next(q for q in contract["paragraphs"][0]["qas"] if "Termination For Convenience" in q["question"])
    print("the experts' termination-for-convenience span:", [a["text"] for a in expert["answers"]])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
