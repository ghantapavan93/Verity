"""Write the API's OpenAPI document to the repository root, so the interface's types can be
generated from it (`npm run api:types`). The backend schema is the source of truth; the
generated file is committed so the frontend builds without a running API.

    cd backend && .venv/Scripts/python scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.main import create_app  # noqa: E402


def main() -> int:
    app = create_app()
    document = app.openapi()
    target = BACKEND.parent / "openapi.json"
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {target} ({len(document.get('paths', {}))} paths, {len(document.get('components', {}).get('schemas', {}))} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
