"""Families from fingerprints: pairwise similarity, single-linkage clustering at a threshold, and
the measurement of both against hand labels. Deterministic; no model."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from itertools import combinations
from pathlib import Path

from sqlalchemy.orm import Session

from ..ingest import PARSER_VERSION
from ..models import Document
from ..schemas import FamiliesOut, FamilyEvaluation, FamilyOut, FamilyPair, FamilyThresholdPoint
from .fingerprint import WEIGHTS, Fingerprint, Similarity, fingerprint, similarity

LABELS_PATH = Path(__file__).with_name("labels.json")
# The highest threshold at which the template label set keeps precision 1.0 on the public corpus (docs/FAMILIES.md).
DEFAULT_THRESHOLD = 0.15
SWEEP = [round(0.05 * i, 2) for i in range(1, 20)]


@dataclass(frozen=True)
class LabelSet:
    name: str
    description: str
    families: tuple[frozenset[str], ...]

    def same_family(self, a: str, b: str) -> bool:
        return any(a in family and b in family for family in self.families)


@dataclass(frozen=True)
class Labels:
    note: str
    documents: dict[str, str]  # label name → first sixteen hex digits of the document's sha256
    sets: tuple[LabelSet, ...]


def load_labels(path: Path = LABELS_PATH) -> Labels:
    data = json.loads(path.read_text(encoding="utf-8"))
    sets = tuple(
        LabelSet(name=name, description=str(body.get("description", "")), families=tuple(frozenset(members) for members in body["families"]))
        for name, body in data["sets"].items()
    )
    return Labels(note=str(data.get("note", "")), documents={str(k): str(v) for k, v in data["documents"].items()}, sets=sets)


def labeled_documents(session: Session, labels: Labels) -> dict[str, Document]:
    """The labeled documents present in the store, by content hash, as read by the current reader."""
    found: dict[str, Document] = {}
    for name, prefix in labels.documents.items():
        document = (
            session.query(Document)
            .filter(Document.sha256.startswith(prefix), Document.parser_version == PARSER_VERSION)
            .order_by(Document.created_at.desc())
            .first()
        )
        if document is not None:
            found[name] = document
    return found


# Documents are immutable, so a fingerprint computed once for a document id stays right; the labeled
# corpus includes a 2,659-section document that took the endpoint to two seconds without this.
_FINGERPRINTS: dict[str, Fingerprint] = {}


def cached_fingerprint(document: Document, name: str) -> Fingerprint:
    cached = _FINGERPRINTS.get(document.id)
    if cached is None:
        cached = _FINGERPRINTS[document.id] = fingerprint(document, name)
    return replace(cached, name=name)


def pairwise(prints: list[Fingerprint]) -> dict[tuple[str, str], Similarity]:
    return {(a.name, b.name): similarity(a, b) for a, b in combinations(prints, 2)}


def cluster(names: list[str], pairs: dict[tuple[str, str], Similarity], threshold: float) -> list[frozenset[str]]:
    """Single linkage: two documents share a family when a chain of pairs at or above the threshold joins them."""
    parent = {name: name for name in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), sim in pairs.items():
        if sim.combined >= threshold:
            parent[find(a)] = find(b)
    groups: dict[str, set[str]] = {}
    for name in names:
        groups.setdefault(find(name), set()).add(name)
    return sorted((frozenset(g) for g in groups.values()), key=lambda g: (-len(g), sorted(g)))


def evaluate(names: list[str], pairs: dict[tuple[str, str], Similarity], threshold: float, label_set: LabelSet) -> tuple[float, float, float]:
    """Pairwise precision, recall and F1 of 'same family' at the threshold against the label set."""
    tp = fp = fn = 0
    for (a, b), sim in pairs.items():
        predicted = sim.combined >= threshold
        actual = label_set.same_family(a, b)
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif actual and not predicted:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return round(precision, 3), round(recall, 3), round(f1, 3)


def report(session: Session, threshold: float = DEFAULT_THRESHOLD, labels: Labels | None = None) -> FamiliesOut:
    labels = labels or load_labels()
    present = labeled_documents(session, labels)
    missing = [name for name in labels.documents if name not in present]
    if len(present) < 2:
        return FamiliesOut(
            available=False,
            detail="Fewer than two labeled documents are in the store; run `scripts/cluster_corpus.py` over the corpus first.",
            threshold=threshold,
            weights=WEIGHTS,
            missing=missing,
        )
    prints = [cached_fingerprint(present[name], name) for name in labels.documents if name in present]
    names = [p.name for p in prints]
    pairs = pairwise(prints)
    families = cluster(names, pairs, threshold)
    by_name = {p.name: p for p in prints}

    def family_out(members: frozenset[str]) -> FamilyOut:
        inner = [pairs[key].combined for key in pairs if key[0] in members and key[1] in members]
        return FamilyOut(
            members=sorted(members),
            titles=[by_name[m].title for m in sorted(members)],
            min_similarity=min(inner) if inner else None,
            max_similarity=max(inner) if inner else None,
        )

    evaluations: list[FamilyEvaluation] = []
    for label_set in labels.sets:
        precision, recall, f1 = evaluate(names, pairs, threshold, label_set)
        sweep = [FamilyThresholdPoint(threshold=t, precision=p, recall=r, f1=f) for t in SWEEP for (p, r, f) in [evaluate(names, pairs, t, label_set)]]
        best = max(sweep, key=lambda point: (point.f1, point.threshold))
        evaluations.append(
            FamilyEvaluation(
                label_set=label_set.name,
                description=label_set.description,
                labeled_pairs=sum(1 for (a, b) in pairs if label_set.same_family(a, b)),
                precision=precision,
                recall=recall,
                f1=f1,
                best_threshold=best.threshold,
                best_f1=best.f1,
                sweep=sweep,
            )
        )
    top_pairs = sorted(pairs.items(), key=lambda item: -item[1].combined)[:15]
    return FamiliesOut(
        available=True,
        threshold=threshold,
        weights=WEIGHTS,
        documents=len(prints),
        missing=missing,
        families=[family_out(f) for f in families],
        pairs=[
            FamilyPair(a=a, b=b, combined=sim.combined, shingles=sim.shingles, headings=sim.headings, terms=sim.terms, labeled=labels.sets[0].same_family(a, b))
            for (a, b), sim in top_pairs
        ],
        evaluations=evaluations,
        note=labels.note,
    )
