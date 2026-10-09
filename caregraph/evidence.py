"""Evidence graph + reference verification.

The verifier is the safety core of CAREGRAPH: a claim may only be shown as
supported if every id it cites resolves to a real extracted fact AND the claim's
numbers appear in that fact. Anything else is downgraded, never dropped silently.
"""
from __future__ import annotations

import re

from .schemas import Case, Claim, EvidenceStatus, Flag, FlagSeverity, GapItem, Question

NODE_DOC = "document"
NODE_FACT = "fact"
NODE_CLAIM = "claim"
NODE_FLAG = "flag"
NODE_QUESTION = "question"

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    """Numeric tokens in a string, normalised so 7.20 == 7.2."""
    out = set()
    for tok in _NUM_RE.findall(text):
        try:
            out.add(f"{float(tok):g}")
        except ValueError:
            pass
    return out


def verify_claim(case: Case, claim: Claim) -> Claim:
    """Assign an evidence status by deterministic checking. No model self-scoring."""
    known = case.fact_ids()
    cited = list(dict.fromkeys(claim.evidence_ids))
    resolved = [cid for cid in cited if cid in known]
    dangling = [cid for cid in cited if cid not in known]

    claim.rejected_evidence_ids = dangling

    if claim.is_general_education:
        claim.status = EvidenceStatus.INSUFFICIENT
        claim.caveat = "General educational information, not drawn from your documents."
        claim.evidence_ids = resolved
        return claim

    if not cited:
        claim.status = EvidenceStatus.UNVERIFIED
        claim.caveat = "This statement cites no source and is shown as unverified."
        return claim

    if dangling:
        claim.evidence_ids = resolved
        claim.status = EvidenceStatus.UNVERIFIED if not resolved else EvidenceStatus.PARTIAL
        claim.caveat = (
            f"{len(dangling)} cited source reference(s) do not exist in the uploaded documents "
            f"and were rejected."
        )
        if not resolved:
            return claim

    # every number asserted by the claim must appear in the cited source text
    claim_numbers = _numbers(claim.text)
    source_numbers: set[str] = set()
    for fid in resolved:
        fact = case.fact(fid)
        if fact is None:
            continue
        source_numbers |= _numbers(fact.provenance.raw_text)
        value = getattr(fact, "value", None)
        if value is not None:
            source_numbers.add(f"{float(value):g}")
    unsupported = claim_numbers - source_numbers

    # a flagged conflict touching the cited evidence outranks a clean match
    conflicting = any(
        f.severity is FlagSeverity.POSSIBLE and set(f.evidence_ids) & set(resolved)
        for f in case.flags
    )

    if conflicting:
        claim.status = EvidenceStatus.CONFLICTING
        claim.caveat = (claim.caveat or "") + (
            " The cited records are themselves flagged as potentially conflicting."
        ).strip()
    elif unsupported:
        claim.status = EvidenceStatus.PARTIAL
        claim.caveat = (
            f"The value(s) {', '.join(sorted(unsupported))} in this statement were not found "
            f"verbatim in the cited source."
        )
    elif claim.status is not EvidenceStatus.PARTIAL:
        claim.status = EvidenceStatus.SUPPORTED
        claim.caveat = claim.caveat or (
            "The wording above is traceable to the cited source text. This confirms the record, "
            "not that any clinical interpretation of it is correct."
        )
    return claim


def verify_all(case: Case) -> Case:
    case.claims = [verify_claim(case, c) for c in case.claims]
    return case


def build_graph(case: Case) -> dict:
    """Return {'nodes': [...], 'edges': [...]} for the interactive graph."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(node_id: str, kind: str, label: str, **extra) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append({"id": node_id, "kind": kind, "label": label, **extra})

    for d in case.documents:
        add_node(d.doc_id, NODE_DOC, d.filename,
                 detail=f"{d.doc_type or 'Untyped'} · {d.doc_date or 'no date'}",
                 doc_id=d.doc_id)

    for m in case.measurements:
        label = f"{m.display_name} {m.value:g} {m.unit or ''}".strip()
        add_node(m.fact_id, NODE_FACT, label, detail=m.provenance.raw_text,
                 doc_id=m.provenance.doc_id, fact_type="measurement")
        edges.append({"source": m.provenance.doc_id, "target": m.fact_id, "relation": "contains"})

    for s in case.statements:
        add_node(s.fact_id, NODE_FACT, s.text[:60], detail=s.provenance.raw_text,
                 doc_id=s.provenance.doc_id, fact_type=s.category)
        edges.append({"source": s.provenance.doc_id, "target": s.fact_id, "relation": "contains"})

    for c in case.claims:
        add_node(c.claim_id, NODE_CLAIM, c.text[:70], detail=c.text,
                 status=c.status.value, caveat=c.caveat)
        for fid in c.evidence_ids:
            if fid in seen:
                edges.append({"source": c.claim_id, "target": fid, "relation": "supported_by"})

    for f in case.flags:
        add_node(f.flag_id, NODE_FLAG, f.title, detail=f.reason,
                 severity=f.severity.value, kind_detail=f.kind.value)
        for fid in f.evidence_ids:
            if fid in seen:
                edges.append({"source": f.flag_id, "target": fid, "relation": "flags"})

    for q in case.questions:
        add_node(q.question_id, NODE_QUESTION, q.text[:70], detail=q.rationale)
        for fid in q.evidence_ids:
            if fid in seen:
                edges.append({"source": q.question_id, "target": fid, "relation": "asks_about"})

    # an edge may never point at a node that does not exist
    valid = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in valid and e["target"] in valid]
    return {"nodes": nodes, "edges": edges}


def graph_integrity(case: Case) -> dict:
    """Counts the UI shows so a judge can audit the verifier's own behaviour."""
    known = case.fact_ids()
    rejected = sum(len(c.rejected_evidence_ids) for c in case.claims)
    by_status: dict[str, int] = {}
    for c in case.claims:
        by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
    return {
        "documents": len(case.documents),
        "facts": len(known),
        "claims": len(case.claims),
        "flags": len(case.flags),
        "questions": len(case.questions),
        "rejected_references": rejected,
        "claims_by_status": by_status,
    }
