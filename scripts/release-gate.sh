#!/usr/bin/env bash
# Release gate: a fresh clone of one commit, new backend and frontend environments, every check the release rests on.
#
#   bash scripts/release-gate.sh <commit>             # clones this repository into $GATE_DIR/clone (../verity-gate)
#   GATE_DIR=/some/scratch bash scripts/release-gate.sh <commit>
#
# Every step records its own exit status, and the gate exits non-zero when any step failed, naming each one. Until
# 2026-10-10 the gate printed each step's last line and kept no status, so a candidate with a failing backend test and
# two failing browser flows ended with exit 0. A line of output is never taken as the verdict; an exit status is, and
# where a tool's own success is a count (the exporter's record) the count is checked.
set -u
set -o pipefail

SHA="${1:?usage: release-gate.sh <commit>}"
SRC="$(cd "$(dirname "$0")/.." && git rev-parse --show-toplevel)"
# Beside the repository by default, not under a temp folder: on Windows `python -m venv` fails at ensurepip under a path
# with a short-name component (C:\Users\NAME~1\AppData\..., README).
GATE_DIR="${GATE_DIR:-$(dirname "$SRC")/verity-gate}"
CLONE="$GATE_DIR/clone"
FAILED=()
# check <name> <status>: a step passes only on status 0.
check() { if [ "$2" -eq 0 ]; then echo "  -> PASS: $1"; else echo "  -> FAIL: $1 (status $2)"; FAILED+=("$1"); fi; }
venv_python() { if [ -x "$1/Scripts/python.exe" ] || [ -x "$1/Scripts/python" ]; then echo "$1/Scripts/python"; else echo "$1/bin/python"; fi; }

mkdir -p "$GATE_DIR"
rm -rf "$CLONE" "$GATE_DIR/verity-export"
[ -e "$CLONE" ] && { echo "GATE ABORTED: $CLONE could not be removed (a process still holds it)"; exit 1; }
git clone -q "$SRC" "$CLONE" && cd "$CLONE" && git checkout -q "$SHA" && echo "HEAD $(git rev-parse HEAD)" \
  || { echo "GATE ABORTED: no clean clone of $SHA from $SRC"; exit 1; }
echo "porcelain lines before anything: $(git status --porcelain | wc -l)"
git diff --name-only HEAD~1 HEAD | sed 's/^/  changed by the last commit: /'

echo "== backend: a fresh environment from the committed lock"
cd "$CLONE/backend"
# The lock the workstation's API and the cloud image both install (README; deploy/cloud/Dockerfile.api), not the newest
# versions on the day: until 2026-10-12 the gate tested FastAPI 0.143 while the workstation ran 0.141 (cloud review).
python -m venv .venv >/dev/null && "$(venv_python .venv)" -m pip install -q -r requirements.lock -r requirements-dev.txt 2>&1 | grep -v -i notice | tail -3
check "backend environment" "${PIPESTATUS[0]}"
PY="$(venv_python .venv)"
echo "== backend: full suite"
$PY -m pytest -q -p no:cacheprovider -rf 2>&1 | grep -E "^(FAILED|ERROR) |passed|failed|error" | tail -12
check "backend full suite" "${PIPESTATUS[0]}"
echo "== backend: workspace isolation, run immutability, trust, export (named)"
$PY -m pytest -q -p no:cacheprovider tests/test_workspaces.py tests/test_trust.py tests/test_run_identity.py tests/test_run_invariants_stateful.py tests/test_review_evidence_export.py 2>&1 | tail -1
check "backend named suites" "${PIPESTATUS[0]}"
echo "== backend: lint, format, types"
$PY -m ruff check . 2>&1 | tail -1; check "ruff check" "${PIPESTATUS[0]}"
$PY -m ruff format --check . 2>&1 | tail -1; check "ruff format" "${PIPESTATUS[0]}"
$PY -m mypy app scripts/export_review_evidence.py tests/test_review_evidence_export.py 2>&1 | tail -1; check "mypy" "${PIPESTATUS[0]}"
# The layering the README promises (.importlinter: verifier pure, providers blind, layers downward); not gated until 2026-10-11.
"$(dirname "$PY")/lint-imports" 2>&1 | tail -1; check "import contracts" "${PIPESTATUS[0]}"
echo "== backend: version-aware trust fault matrix"
$PY scripts/trust_faults.py 2>&1 | tail -3; check "trust fault matrix (every fault caught, every file restored)" "${PIPESTATUS[0]}"
dirty=$(git status --porcelain | wc -l)
echo "tracked files changed by the fault run (0 = every fault was put back): $dirty"
[ "$dirty" -eq 0 ]; check "fault run left the tree clean" $?

echo "== frontend: a fresh install"
cd "$CLONE"
npm ci --no-audit --no-fund > "$GATE_DIR/npm-ci.log" 2>&1; s=$?; echo "npm ci exit $s"; check "npm ci" $s
echo "== frontend: unit tests"
npx vitest run > "$GATE_DIR/vitest.log" 2>&1; s=$?
grep -E "Tests|Test Files" "$GATE_DIR/vitest.log" | sed 's/\x1b\[[0-9;]*m//g'; check "frontend unit tests" $s
echo "== frontend: lint and types"
npm run lint > "$GATE_DIR/lint.log" 2>&1; s=$?; echo "eslint exit $s"; check "eslint" $s
npm run typecheck > "$GATE_DIR/tsc.log" 2>&1; s=$?; echo "tsc exit $s"; check "tsc" $s
echo "== frontend: production build"
npm run build > "$GATE_DIR/build.log" 2>&1; s=$?; echo "build exit $s"; check "production build" $s
echo "== browser flows"
# Port 8001 can be taken on a developer machine (a Docker stack, 2026-10-08), and Playwright would reuse it as the API.
# The flows run on 8011/3911 from a copy of the config; the copy, its build and the tsconfig Next rewrites are removed.
# The copy never reuses a server: on 2026-10-13 a replay stack left on 8011/3911 by another task answered every gate's
# flows for hours, so the gate tested that stack and not the commit (war-room counter-review). A taken port now fails.
sed -e "s/const API_PORT = 8001;/const API_PORT = 8011;/" -e "s/const WEB_PORT = 3901;/const WEB_PORT = 3911;/" -e "s/NEXT_DIST_DIR: \".next-e2e\"/NEXT_DIST_DIR: \".next-e2e-gate\"/" -e "s/reuseExistingServer: !process.env.CI/reuseExistingServer: false/g" playwright.config.ts > pw-gate.config.ts
grep -q "reuseExistingServer: false" pw-gate.config.ts && ! grep -q "reuseExistingServer: !" pw-gate.config.ts; check "browser flows start their own servers" $?
sed -i -e "s#127.0.0.1:8001#127.0.0.1:8011#g" -e "s#localhost:3901#localhost:3911#g" e2e/*.spec.ts  # specs that name the API port
npx playwright test -c pw-gate.config.ts > "$GATE_DIR/playwright.log" 2>&1; s=$?; echo "playwright exit $s (ports 8011/3911)"
rm -f pw-gate.config.ts; rm -rf .next-e2e-gate; git checkout -q -- tsconfig.json e2e
grep -E "^\s+[0-9]+ (passed|failed|flaky|skipped)|^\s+[0-9]+\) \[" "$GATE_DIR/playwright.log" | sed 's/\x1b\[[0-9;]*m//g' | head -20
check "browser flows" $s

echo "== the evidence exporter, from this checkout, with the configured local model"
cd "$CLONE/backend"
$PY scripts/export_review_evidence.py --out "$GATE_DIR/verity-export" 2>&1 | tail -1; check "evidence exporter" "${PIPESTATUS[0]}"
$PY - "$GATE_DIR/verity-export" <<'EOF'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
m = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
s = json.loads((out / "records" / "review-snapshot.json").read_text(encoding="utf-8"))
print("  bundle names commit:", m["source_commit"], "| producer:", m["producer"])
print("  model:", s["run"]["model"], "| findings:", len(s["run"]["findings"]), "| trust:", s["trust"]["counts"], "| diff:", s["diff"]["counts"])
print("  model calls before the revision:", s["model_calls"]["before_the_revision"], "| after:", s["model_calls"]["after_the_revision"])
same = s["run_record_sha256"]["before_the_diff"] == s["run_record_sha256"]["after_the_diff"]
print("  run record identical before and after the diff:", same)
sys.exit(0 if same and s["model_calls"]["after_the_revision"] == 0 else 1)
EOF
check "exported run record unchanged by the diff, no model call after the revision" $?
cd "$CLONE"
expected=$(git log -1 --format=%H -- backend/scripts/export_review_evidence.py backend/scripts/revision_evidence/)
named=$(grep -o '"source_commit": "[0-9a-f]*"' "$GATE_DIR/verity-export/bundle.json" | grep -o '[0-9a-f]\{40\}')
echo "exporter named the last commit that changed the exporter or its fixtures ($(git rev-parse --short "$expected")): $([ "$named" = "$expected" ] && echo yes || echo NO)"
[ "$named" = "$expected" ]; check "exporter names its commit" $?
dirty=$(git status --porcelain | wc -l)
echo "porcelain lines at the end (0 = clean; the export went outside the repository): $dirty"
git status --porcelain | head -5
[ "$dirty" -eq 0 ]; check "clean tree at the end" $?

echo
if [ "${#FAILED[@]}" -eq 0 ]; then
  echo "GATE PASSED: $SHA"
  exit 0
fi
echo "GATE FAILED: $SHA (${#FAILED[@]} step(s))"
printf '  - %s\n' "${FAILED[@]}"
exit 1
