"""The rollout SkillOpt optimises against: the workbench's own answer path, end to end, scored by the
CUAD rule. Retrieval, prompt assembly, the model call (our Ollama provider: temperature 0, a fixed
seed, thinking off, the JSON schema), parsing with one corrected retry, verification of every quote
against the section text and the status decision are the production functions. Only the system prompt
changes: it is the skill under optimisation.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.analysis.service import PromptPackage, SectionForPrompt, analyze, build_user_message
from app.batch.cuad_match import hits, retrieved_carries
from app.config import settings
from app.hashing import sha256_text
from app.ingest import ingest
from app.providers import make_provider
from app.providers.base import ModelProvider, ProviderError
from app.retrieval.lexical import LexicalIndex
from app.runs.service import verify_evidence
from app.runs.status import decide

SOFT = {"correct": 1.0, "correct absence": 1.0, "cited elsewhere": 0.5}


@dataclass(frozen=True)
class Sec:
    """What the prompt builder and the verifier need from a section: the fields the ORM row carries."""

    id: str
    ordinal: int
    number: str
    heading: str
    text: str


_provider: ModelProvider | None = None
_sections: dict[str, list[Sec]] = {}


def provider() -> ModelProvider:
    global _provider  # one provider per process, created on first use
    if _provider is None:
        _provider = make_provider("ollama")
    return _provider


def sections_of(contract_file: str) -> list[Sec]:
    cached = _sections.get(contract_file)
    if cached is None:
        path = Path(contract_file)
        parsed = ingest(path.name, path.read_bytes())
        cached = [Sec(id=f"{parsed.sha256[:12]}:{i}", ordinal=i, number=s.number, heading=s.heading, text=s.text) for i, s in enumerate(parsed.sections)]
        _sections[contract_file] = cached
    return cached


def retrieve(sections: list[Sec], question: str, k: int) -> list[Sec]:
    index = LexicalIndex([(s.heading, s.text) for s in sections])
    candidates = index.search(question, k)
    if not candidates and sections:
        return sections[: min(k, len(sections))]
    return [sections[c.index] for c in candidates]


def classify(answered: bool, located: list[str], experts: list[str]) -> str:
    if answered and not experts:
        return "asserted where experts found none"
    if answered:
        return "correct" if any(hits(text, experts) for text in located) else "cited elsewhere"
    return "missed" if experts else "correct absence"


def rollout_one(item: dict[str, Any], skill: str, prediction_dir: Path) -> dict[str, Any]:
    sections = sections_of(str(item["contract_file"]))
    chosen = retrieve(sections, str(item["question"]), settings.retrieval_k)
    by_label = {f"sec_{s.ordinal}": s for s in chosen}
    user = build_user_message(
        str(item["question"]), None, str(item["contract_name"]), [SectionForPrompt(label, s.number, s.heading, s.text) for label, s in by_label.items()]
    )
    prompt = PromptPackage(version="skillopt-candidate", system=skill, sha256=sha256_text(skill))
    experts: list[str] = [str(e) for e in item.get("expert_spans") or []]

    raw = ""
    attempts = 0
    conclusion = ""
    citation = ""
    located_texts: list[str] = []
    answered = False
    not_found = False
    detail = ""
    started = time.perf_counter()
    try:
        result = analyze(provider(), prompt, user)
        raw = result.generation.text
        attempts = result.attempts
        if result.proposal is None:
            outcome = "invalid output"
            detail = result.validation_error or ""
        else:
            for finding in result.proposal.findings:
                all_verified = bool(finding.evidence)
                found: list[tuple[Sec, str]] = []
                for evidence in finding.evidence:
                    section, located, _method = verify_evidence(evidence.quote, evidence.section_id, by_label, chosen)  # type: ignore[arg-type]
                    if located is None or section is None:
                        all_verified = False
                    else:
                        found.append((section, section.text[located.start : located.end]))
                decision = decide(finding.status_hint, finding.observed, finding.required, False, all_verified)
                if decision.status in ("pass", "needs_review") and found and not answered:
                    answered = True
                    conclusion = finding.conclusion
                    first = found[0][0]
                    citation = f"§{first.number}" if first.number else first.heading
                    located_texts = [text for _section, text in found]
                elif decision.status == "missing":
                    not_found = True
                    conclusion = conclusion or finding.conclusion
            outcome = classify(answered, located_texts, experts)
    except ProviderError as error:
        outcome = "failed"
        detail = str(error)
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    expert_head = experts[0][:160] if experts else ""
    if outcome == "cited elsewhere":
        fail_reason = f"the verified citation {citation} ({located_texts[0][:120]!r}) does not overlap any expert span; the experts marked: {expert_head!r}"
    elif outcome == "missed":
        carried = any(retrieved_carries(s.text, e) for s in chosen for e in experts)
        carried_text = "yes" if carried else "no"
        fail_reason = f"answered 'not found' or was withheld, but the experts marked: {expert_head!r}; a retrieved section carried that span: {carried_text}"
    elif outcome == "asserted where experts found none":
        fail_reason = f"asserted {conclusion[:120]!r} citing {citation}, but the experts found no such clause in this contract"
    elif outcome == "invalid output":
        fail_reason = f"the answer was not valid JSON for the schema after {attempts} attempts: {detail[:200]}"
    elif outcome == "failed":
        fail_reason = f"provider error: {detail[:200]}"
    else:
        fail_reason = ""

    if answered:
        predicted = f"{conclusion} [{citation}]"
    elif not_found:
        predicted = f"not found: {conclusion}"
    else:
        predicted = "no finding shown (withheld, insufficient evidence, or invalid output)"

    task_dir = prediction_dir / str(item["id"])
    task_dir.mkdir(parents=True, exist_ok=True)
    conversation = [{"role": "system", "content": skill}, {"role": "user", "content": user}, {"role": "assistant", "content": raw}]
    (task_dir / "conversation.json").write_text(json.dumps(conversation, ensure_ascii=False, indent=1), encoding="utf-8")

    return {
        "id": str(item["id"]),
        "hard": 1 if outcome in ("correct", "correct absence") else 0,
        "soft": SOFT.get(outcome, 0.0),
        "predicted_answer": predicted,
        "task_description": f"{item['category']}: {item['question']} (contract: {item['title']})",
        "question": str(item["question"]),
        "task_type": str(item["task_type"]),
        "fail_reason": fail_reason,
        "reference_text": ("\n---\n".join(experts))[:800] if experts else "(the experts found no clause of this category in this contract)",
        "target_system_prompt": skill,
        "target_user_prompt": user,
        "n_turns": 1,
        "outcome": outcome,
        "citation": citation,
        "latency_ms": latency_ms,
        "attempts": attempts,
    }


def run_batch(*, items: list[dict[str, Any]], skill_content: str, out_root: str, workers: int = 1, max_completion_tokens: int = 0) -> list[dict[str, Any]]:
    """One GPU serves the model, so the rollout is sequential whatever ``workers`` says."""
    del workers, max_completion_tokens
    root = Path(out_root)
    prediction_dir = root / "predictions"
    prediction_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        result = rollout_one(item, skill_content, prediction_dir)
        results.append(result)
        print(f"  [{index}/{len(items)}] {item['id'][:48]:48} {result['outcome']:34} {result['latency_ms'] / 1000:5.1f} s", flush=True)
    (root / "rollouts.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    correct = sum(r["hard"] for r in results)
    print(f"  batch: {correct}/{len(results)} correct", flush=True)
    return results
