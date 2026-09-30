"""Record the golden set: one run per golden per prompt version, through the same start_run use
case the interface uses, against the live provider. Runs that already exist are reused, so the
script is safe to repeat; it prints a verdict per golden and a pass count per prompt version.

    cd backend && .venv/Scripts/python scripts/run_goldens.py                      # current prompt and model
    cd backend && .venv/Scripts/python scripts/run_goldens.py --prompt answer-v1 --prompt answer-v2
    cd backend && .venv/Scripts/python scripts/run_goldens.py --prompt answer-v2 --model qwen3:4b
    cd backend && .venv/Scripts/python scripts/run_goldens.py --only g01 --only g06
    cd backend && .venv/Scripts/python scripts/run_goldens.py --report             # no runs: the prompt regression report
    cd backend && .venv/Scripts/python scripts/run_goldens.py --compare-models qwen3:8b qwen3:4b   # the routing question

The kill rule that reads these numbers is in docs/GOLDENS.md; the routing rule in docs/ROUTING.md.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.analysis.service import load_prompt  # noqa: E402
from app.application.save_guidance import save_guidance  # noqa: E402
from app.application.start_run import start_run  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.goldens.service import compare_models, ensure_golden_document, judge, load_set, report, run_for, task_of  # noqa: E402
from app.providers import make_provider  # noqa: E402
from app.runs.service import execute_run  # noqa: E402


def print_report() -> int:
    """Improvements, regressions, unchanged passes and failures, latency delta: the head prompt against the previous one."""
    with SessionLocal() as session:
        out = report(session)
    if not out.available or not out.prompts:
        print(out.detail or "nothing recorded")
        return 1
    for prompt in out.prompts:
        latency = f" · mean model latency {prompt.mean_latency_ms / 1000:.1f} s" if prompt.mean_latency_ms else ""
        print(f"{prompt.version} ({prompt.hash[:12]}): {prompt.passes} of {prompt.recorded} pass{latency}")
        for count in prompt.by_category:
            print(f"    {count.category:<22} {count.passes}/{count.recorded}")
    compare = out.compare
    if compare is None:
        print("\none prompt version recorded; nothing to compare")
        return 0
    rows = {r.golden_id: r for r in compare.rows}
    improvements = [g for g, r in rows.items() if r.change == "better"]
    regressions = [g for g, r in rows.items() if r.change == "worse"]
    same_pass = [g for g, r in rows.items() if r.change == "same" and r.head == "pass" and r.base == "pass"]
    same_fail = [g for g, r in rows.items() if r.change == "same" and r.head == "fail" and r.base == "fail"]
    print(f"\n{compare.head} against {compare.base}")
    print(f"  improvements       {len(improvements):>3}  {' '.join(improvements)}")
    print(f"  regressions        {len(regressions):>3}  {' '.join(regressions)}")
    print(f"  unchanged passes   {len(same_pass):>3}")
    print(f"  unchanged failures {len(same_fail):>3}  {' '.join(same_fail)}")
    print(f"  different citations or statuses with the same verdict: {compare.changed}")
    if compare.latency_delta_ms is not None:
        print(f"  mean latency delta {compare.latency_delta_ms / 1000:+.1f} s")
    if improvements and not regressions:
        verdict = "kept"
    elif improvements:
        verdict = "kept only if each regression is accepted in writing"
    else:
        verdict = "not kept: no improvement"
    print(f"  under the rule: {verdict}")
    return 0


def print_model_report(prompt_version: str, base_model: str, candidate_model: str) -> int:
    """The routing question, answered per task: does the candidate pass every golden the default passes, and how fast?"""
    with SessionLocal() as session:
        out = compare_models(session, prompt_version, base_model, candidate_model)
    rows = {r.golden_id: r for r in out.compare.rows}
    golden_task = {g.id: task_of(g) for g in load_set().goldens}
    print(f"prompt {out.prompt_version} · {out.candidate_model} against {out.base_model}")
    tasks = sorted(set(out.base_by_task) | set(out.candidate_by_task))
    for task in tasks:
        b = out.base_by_task.get(task, (0, 0))
        c = out.candidate_by_task.get(task, (0, 0))
        print(f"  {task:<20} {out.base_model}: {b[0]}/{b[1]}   {out.candidate_model}: {c[0]}/{c[1]}")
    regressions = [g for g, r in rows.items() if r.change == "worse"]
    improvements = [g for g, r in rows.items() if r.change == "better"]
    print(f"  candidate worse on  {len(regressions):>3}  {' '.join(regressions)}")
    print(f"  candidate better on {len(improvements):>3}  {' '.join(improvements)}")
    if out.base_latency_ms and out.candidate_latency_ms:
        print(f"  mean model latency  {out.base_model} {out.base_latency_ms / 1000:.1f} s · {out.candidate_model} {out.candidate_latency_ms / 1000:.1f} s")
    print("  under the rule (docs/ROUTING.md):")
    for task in tasks:
        base_recorded = out.base_by_task.get(task, (0, 0))[1]
        candidate_recorded = out.candidate_by_task.get(task, (0, 0))[1]
        worse_here = [g for g in regressions if golden_task.get(g) == task]
        if candidate_recorded == 0 or candidate_recorded < base_recorded:
            verdict = f"not measured on every golden of the task yet ({candidate_recorded} of {base_recorded})"
        elif worse_here:
            verdict = f"not routed: fails goldens the default passes ({' '.join(worse_here)})"
        else:
            verdict = "may be routed: no golden the default passes fails"
        print(f"    {task:<20} {verdict}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompt", action="append", help="prompt version to run (repeatable); default: the configured one")
    parser.add_argument("--only", action="append", help="golden id to run (repeatable); default: all")
    parser.add_argument("--model", help="model to answer with (recorded in the run's identity); default: the configured one")
    parser.add_argument("--report", action="store_true", help="print the prompt regression report from recorded runs and exit")
    parser.add_argument("--compare-models", nargs=2, metavar=("BASE", "CANDIDATE"), help="print the model comparison for --prompt (default prompt) and exit")
    args = parser.parse_args()
    init_db()
    if args.report:
        return print_report()
    if args.compare_models:
        return print_model_report((args.prompt or [settings.prompt_version])[0], args.compare_models[0], args.compare_models[1])

    versions = args.prompt or [settings.prompt_version]
    golden_set = load_set()
    provider = make_provider(model=args.model, workload="batch")
    ok, detail = provider.healthy()
    if not ok:
        print(f"provider not ready: {detail}")
        return 2

    totals: dict[str, tuple[int, int]] = {}
    with SessionLocal() as session:
        document = ensure_golden_document(session, golden_set)
        print(f"document {document.id} {document.name} sha256 {document.sha256[:16]} · set {golden_set.sha256[:16]} · {len(golden_set.goldens)} goldens")
        for version in versions:
            prompt = load_prompt(version)
            passes = judged = 0
            print(f"\n== prompt {version} ({prompt.sha256[:12]}) · model {provider.model}")
            for golden in golden_set.goldens:
                if args.only and golden.id not in args.only:
                    continue
                guidance_id = save_guidance(session, golden.guidance, source="golden").guidance.id if golden.guidance else None
                started = start_run(session, document.id, guidance_id, golden.question, provider, prompt_version=version, model=args.model)
                if started.created:
                    began = time.perf_counter()
                    execute_run(session, started.run.id, provider)
                    took = f"{time.perf_counter() - began:5.1f} s"
                else:
                    took = "reused"
                session.expire_all()
                verdict = judge(golden, run_for(session, document, golden, prompt, args.model))
                judged += 1
                passes += verdict.outcome == "pass"
                print(f"{golden.id} {golden.category[:12]:<12} {verdict.outcome:<7} {took:>8}  {golden.question[:52]:<52}  {verdict.because}")
            totals[version] = (passes, judged)
    print()
    for version, (passes, judged) in totals.items():
        print(f"{version}: {passes} of {judged} pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
