"""Analysis pipeline: facts -> claims, gaps, questions, appointment brief."""
from __future__ import annotations

import hashlib

from . import contradictions, evidence, timeline
from .llm import LLMResult, ResilientProvider, get_provider
from .safety import DISCLAIMER
from .schemas import (Case, Claim, EvidenceStatus, FlagKind, FlagSeverity, GapItem,
                      Question)
from .units import display_for

# Analytes a record set is commonly expected to carry context for. Used only to
# report absence - CAREGRAPH never fills these in.
EXPECTED_CONTEXT: dict[str, str] = {
    "glucose_fasting": "whether the sample was taken fasting",
    "hba1c": "the assay's reference range",
    "ldl": "whether the sample was taken fasting",
    "bp_systolic": "the position and arm used for the reading",
}

LANGUAGES = {"en": "English", "hi": "Hindi", "mr": "Marathi", "es": "Spanish", "fr": "French"}


def _cid(*p: object) -> str:
    return "c_" + hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:10]


def _qid(*p: object) -> str:
    return "q_" + hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:10]


def build_claims(case: Case) -> list[Claim]:
    """Generate explanations strictly from extracted data.

    Two kinds only: a restatement of a single recorded value, and a description
    of a recorded change over time. Neither asserts what the change means.
    """
    claims: list[Claim] = []

    for series in timeline.build_series(case):
        if len(series.points) >= 2:
            summary = series.change_summary()
            if summary:
                claims.append(Claim(
                    claim_id=_cid("trend", series.analyte),
                    text=summary,
                    evidence_ids=[p.fact_id for p in series.points],
                    generator="deterministic",
                    caveat=("This describes the recorded numbers only. What the change means "
                            "clinically is for a healthcare professional to assess."),
                ))
        for exc_m, reason in series.excluded:
            claims.append(Claim(
                claim_id=_cid("excl", exc_m.fact_id),
                text=(f"{display_for(series.analyte)} of {exc_m.value:g} "
                      f"{exc_m.unit or '(no unit)'} is held out of the chart because {reason}."),
                evidence_ids=[exc_m.fact_id],
                generator="deterministic",
            ))

    for m in case.measurements:
        if m.ref_low is None or m.ref_high is None:
            continue
        inside = m.ref_low <= m.value <= m.ref_high
        where = "within" if inside else "outside"
        claims.append(Claim(
            claim_id=_cid("range", m.fact_id),
            text=(f"{m.display_name} of {m.value:g} {m.unit or ''} is {where} the reference "
                  f"range of {m.ref_low:g}-{m.ref_high:g} printed in this document.").replace("  ", " "),
            evidence_ids=[m.fact_id],
            generator="deterministic",
            caveat=("Compared against the range printed on this report only. Reference ranges "
                    "differ between laboratories."),
        ))
    return claims


def build_gaps(case: Case) -> list[GapItem]:
    """Describe what is absent. Never invents the missing content."""
    gaps: list[GapItem] = []

    undated = [d for d in case.documents if d.doc_date is None and d.text.strip()]
    if undated:
        gaps.append(GapItem(
            gap_id="g_undated", label="Documents without a readable date",
            detail=(f"{len(undated)} document(s) carry no date CAREGRAPH could read, so their "
                    f"contents cannot be placed in sequence."),
            related_doc_ids=[d.doc_id for d in undated],
        ))

    no_range = sorted({m.analyte for m in case.measurements if m.ref_low is None})
    if no_range:
        gaps.append(GapItem(
            gap_id="g_noranges", label="Results with no reference range",
            detail=("No reference range is printed for: "
                    + ", ".join(display_for(a) for a in no_range)
                    + ". Without it, these values cannot be judged normal or abnormal from the record."),
            related_doc_ids=sorted({m.provenance.doc_id for m in case.measurements if m.ref_low is None}),
        ))

    present = {m.analyte for m in case.measurements}
    for analyte, what in EXPECTED_CONTEXT.items():
        if analyte not in present:
            continue
        items = [m for m in case.measurements if m.analyte == analyte]
        if analyte in ("glucose_fasting", "ldl") and all(m.context is None for m in items):
            gaps.append(GapItem(
                gap_id=f"g_ctx_{analyte}", label=f"{display_for(analyte)}: sampling context not stated",
                detail=f"The record does not state {what}.",
                related_doc_ids=sorted({m.provenance.doc_id for m in items}),
            ))

    singles = [a for a in present if sum(1 for m in case.measurements if m.analyte == a) == 1]
    if singles:
        gaps.append(GapItem(
            gap_id="g_single", label="Measured once only",
            detail=("Only one reading exists for: " + ", ".join(sorted(display_for(a) for a in singles))
                    + ". No change over time can be described for these."),
            related_doc_ids=[],
        ))

    if not case.statements:
        gaps.append(GapItem(
            gap_id="g_nostatements", label="No medications or instructions found",
            detail=("No medication lines, instructions or recorded observations were extracted. "
                    "The uploaded documents may be results-only."),
            related_doc_ids=[],
        ))
    return gaps


def build_questions(case: Case) -> list[Question]:
    """Prioritised questions for a clinician, each anchored to real evidence."""
    questions: list[Question] = []

    for flag in case.flags:
        priority = 1 if flag.severity is FlagSeverity.POSSIBLE else 3
        questions.append(Question(
            question_id=_qid("flag", flag.flag_id),
            text=flag.needs_clarification,
            priority=priority,
            evidence_ids=flag.evidence_ids,
            rationale=f"Raised by: {flag.title}",
        ))

    for m in case.measurements:
        if m.ref_low is not None and m.ref_high is not None and not (m.ref_low <= m.value <= m.ref_high):
            questions.append(Question(
                question_id=_qid("out", m.fact_id),
                text=(f"My {m.display_name} was {m.value:g} {m.unit or ''}, outside the "
                      f"{m.ref_low:g}-{m.ref_high:g} range printed on the report. What does that "
                      f"mean for me, and does it need repeating?").replace("  ", " "),
                priority=2,
                evidence_ids=[m.fact_id],
                rationale="A recorded value sits outside the range printed on its own report.",
            ))

    for series in timeline.build_series(case):
        if len(series.points) >= 2:
            first, last = series.points[0], series.points[-1]
            if abs(last.value - first.value) > 1e-9:
                questions.append(Question(
                    question_id=_qid("trend", series.analyte),
                    text=(f"My recorded {series.label} moved from {first.value:g} to "
                          f"{last.value:g} {series.unit or ''}. Is that change expected, and "
                          f"should anything be monitored?").replace("  ", " "),
                    priority=2,
                    evidence_ids=[p.fact_id for p in series.points],
                    rationale="A value changed between documents.",
                ))

    for gap in case.gaps:
        if gap.gap_id in ("g_noranges", "g_undated"):
            questions.append(Question(
                question_id=_qid("gap", gap.gap_id),
                text=f"Could you supply the missing detail: {gap.label.lower()}?",
                priority=3, evidence_ids=[], rationale=gap.detail,
            ))

    seen: set[str] = set()
    unique = [q for q in questions if not (q.question_id in seen or seen.add(q.question_id))]
    unique.sort(key=lambda q: (q.priority, q.text))
    return unique


def analyse(case: Case) -> Case:
    """Run the full deterministic pipeline in dependency order."""
    case.flags = contradictions.run_all(case)      # flags first: claims depend on them
    case.claims = build_claims(case)
    case.gaps = build_gaps(case)
    case.questions = build_questions(case)
    evidence.verify_all(case)
    return case


def explain_facts(case: Case, fact_ids: list[str], language: str = "en",
                  force_offline: bool = False) -> tuple[Claim, LLMResult]:
    """Plain-language explanation of selected facts, verified before return."""
    provider = ResilientProvider(get_provider(force_offline=force_offline))
    payload = []
    for fid in fact_ids:
        fact = case.fact(fid)
        if fact is None:
            continue
        payload.append({
            "fact_id": fact.fact_id,
            "label": getattr(fact, "display_name", None) or getattr(fact, "text", ""),
            "value": getattr(fact, "value", None),
            "unit": getattr(fact, "unit", None),
            "date": fact.observed_on.isoformat() if fact.observed_on else None,
            "ref_low": getattr(fact, "ref_low", None),
            "ref_high": getattr(fact, "ref_high", None),
            "source_text": fact.provenance.raw_text,
        })

    result = provider.explain(
        "Restate these record entries in plain language for a patient.",
        payload, language=LANGUAGES.get(language, "English"),
    )
    if result.explanation is None:
        claim = Claim(
            claim_id=_cid("explain", *fact_ids),
            text="An explanation could not be generated for this selection.",
            evidence_ids=[], generator=result.provider,
        )
    else:
        claim = Claim(
            claim_id=_cid("explain", *fact_ids, result.explanation.plain_language[:40]),
            text=result.explanation.plain_language,
            evidence_ids=result.explanation.evidence_ids,
            caveat=result.explanation.caveat,
            generator=result.provider,
        )
    return evidence.verify_claim(case, claim), result


def appointment_brief(case: Case) -> str:
    """A concise, shareable brief. Every line traceable or marked otherwise."""
    lines: list[str] = ["# Appointment preparation brief", ""]
    synthetic = any(d.is_synthetic for d in case.documents)
    if synthetic:
        lines += ["> **SIMULATED DATA.** This brief was built from synthetic demo records.", ""]

    lines += ["## Documents reviewed", ""]
    for e in timeline.document_events(case):
        when = e["date"].isoformat() if e["date"] else "date not recorded"
        lines.append(f"- {e['filename']} - {e['label']}, {when} "
                     f"({e['n_measurements']} measurements, {e['n_statements']} statements)")

    supported = [c for c in case.claims if c.status is EvidenceStatus.SUPPORTED]
    if supported:
        lines += ["", "## What the records say", ""]
        for c in supported[:12]:
            lines.append(f"- {c.text}  \n  _Evidence: {', '.join(c.evidence_ids) or 'none'}_")

    unresolved = [f for f in case.flags if f.severity is FlagSeverity.POSSIBLE]
    formatting = [f for f in case.flags if f.severity is FlagSeverity.FORMATTING]
    lines += ["", "## Unresolved inconsistencies", ""]
    if unresolved:
        for f in unresolved:
            lines.append(f"- **{f.title}** - {f.reason}  \n  _Needs clarification: {f.needs_clarification}_")
    else:
        lines.append("- None that could be justified from these documents.")
    if formatting:
        lines += ["", f"_Plus {len(formatting)} formatting/completeness inconsistencies "
                      f"(units, missing ranges, unlabelled dates)._"]

    if case.gaps:
        lines += ["", "## Missing information", ""]
        for g in case.gaps:
            lines.append(f"- **{g.label}** - {g.detail}")

    lines += ["", "## Questions to ask", ""]
    for q in case.questions[:12]:
        tag = {1: "High", 2: "Medium", 3: "Low"}.get(q.priority, "Low")
        lines.append(f"- [{tag}] {q.text}")

    lines += ["", "---", "", DISCLAIMER]
    return "\n".join(lines)
