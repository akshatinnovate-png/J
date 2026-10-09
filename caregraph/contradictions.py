"""Contradiction Radar: cross-document consistency checks.

Every finding names both source passages and what a human must clarify.
CAREGRAPH never decides which record is correct.
"""
from __future__ import annotations

import hashlib
import re

from .schemas import Case, Flag, FlagKind, FlagSeverity, Measurement
from .units import comparable, convert, display_for

# relative difference above which two same-day readings are called a conflict
SAME_DAY_TOLERANCE = 0.05
_NEGATION = re.compile(r"(?i)\b(no|denies|without|negative for|not|non[- ])\b")


def _fid(*parts: object) -> str:
    return "f_" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def _label(case: Case, m: Measurement) -> str:
    doc = case.doc(m.provenance.doc_id)
    return f"{doc.filename if doc else m.provenance.doc_id} p{m.provenance.page}"


def check_unit_mismatch(case: Case) -> list[Flag]:
    flags: list[Flag] = []
    by_analyte: dict[str, list[Measurement]] = {}
    for m in case.measurements:
        by_analyte.setdefault(m.analyte, []).append(m)

    for analyte, items in by_analyte.items():
        units = {m.unit_canonical for m in items if m.unit_canonical}
        if len(units) < 2:
            continue
        pairs = sorted(units)
        for i, ua in enumerate(pairs):
            for ub in pairs[i + 1:]:
                a = next(m for m in items if m.unit_canonical == ua)
                b = next(m for m in items if m.unit_canonical == ub)
                convertible = comparable(analyte, ua, ub)
                flags.append(Flag(
                    flag_id=_fid("unit", analyte, ua, ub),
                    kind=FlagKind.UNIT_MISMATCH,
                    severity=FlagSeverity.FORMATTING,
                    title=f"{display_for(analyte)} is recorded in two different units",
                    reason=(
                        f"'{ua}' appears in {_label(case, a)} and '{ub}' in {_label(case, b)}. "
                        + (f"A standard conversion exists, so CAREGRAPH plots both in one unit "
                           f"and shows the original value on hover."
                           if convertible else
                           f"No single agreed conversion factor exists between these units for "
                           f"{display_for(analyte)}, so these readings are NOT plotted together.")
                    ),
                    needs_clarification=(
                        "Confirm with the issuing laboratory which unit each result was reported in."
                        if convertible else
                        "Ask the clinician to restate both results in the same unit before comparing them."
                    ),
                    evidence_ids=[a.fact_id, b.fact_id],
                ))
    return flags


def check_same_day_conflicts(case: Case) -> list[Flag]:
    """Two readings of the same analyte on the same date that disagree materially."""
    flags: list[Flag] = []
    buckets: dict[tuple[str, object], list[Measurement]] = {}
    for m in case.measurements:
        if m.observed_on is None:
            continue
        buckets.setdefault((m.analyte, m.observed_on), []).append(m)

    for (analyte, date), items in buckets.items():
        if len(items) < 2:
            continue
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a.provenance.doc_id == b.provenance.doc_id and a.fact_id == b.fact_id:
                    continue
                if not (a.unit_canonical and b.unit_canonical):
                    continue
                b_conv = convert(analyte, b.value, b.unit_canonical, a.unit_canonical)
                if b_conv is None:
                    continue  # already reported by the unit check
                if (a.context or None) != (b.context or None):
                    continue  # different sampling context; handled separately
                denom = max(abs(a.value), abs(b_conv), 1e-9)
                if abs(a.value - b_conv) / denom <= SAME_DAY_TOLERANCE:
                    continue
                flags.append(Flag(
                    flag_id=_fid("sameday", analyte, date, a.fact_id, b.fact_id),
                    kind=FlagKind.VALUE_CONFLICT,
                    severity=FlagSeverity.POSSIBLE,
                    title=f"Two different {display_for(analyte)} values recorded for {date}",
                    reason=(
                        f"{_label(case, a)} records {a.value:g} {a.unit_canonical or ''} and "
                        f"{_label(case, b)} records {b.value:g} {b.unit_canonical or ''} "
                        f"for the same date. CAREGRAPH cannot determine which record is correct."
                    ),
                    needs_clarification=(
                        "Ask which result corresponds to this date; one document may carry a "
                        "transcription error or a different collection time."
                    ),
                    evidence_ids=[a.fact_id, b.fact_id],
                ))
    return flags


def check_context_incomparable(case: Case) -> list[Flag]:
    """Same analyte compared across different sampling contexts."""
    flags: list[Flag] = []
    by_analyte: dict[str, list[Measurement]] = {}
    for m in case.measurements:
        by_analyte.setdefault(m.analyte, []).append(m)
    for analyte, items in by_analyte.items():
        contexts = {m.context for m in items}
        if len(contexts) > 1 and None in contexts and len(items) > 1:
            unlabelled = [m for m in items if m.context is None]
            labelled = [m for m in items if m.context is not None]
            if not unlabelled or not labelled:
                continue
            flags.append(Flag(
                flag_id=_fid("ctx", analyte),
                kind=FlagKind.INCOMPARABLE_CONTEXT,
                severity=FlagSeverity.FORMATTING,
                title=f"{display_for(analyte)} readings have inconsistent sampling context",
                reason=(
                    f"{_label(case, labelled[0])} states a '{labelled[0].context}' sample, while "
                    f"{_label(case, unlabelled[0])} states no sampling context. These are not "
                    f"necessarily the same quantity, so the unlabelled reading is excluded from the chart."
                ),
                needs_clarification="Ask whether the unlabelled sample was taken under the same conditions.",
                evidence_ids=[labelled[0].fact_id, unlabelled[0].fact_id],
            ))
    return flags


def check_missing_ranges(case: Case) -> list[Flag]:
    flags: list[Flag] = []
    by_analyte: dict[str, list[Measurement]] = {}
    for m in case.measurements:
        by_analyte.setdefault(m.analyte, []).append(m)
    for analyte, items in by_analyte.items():
        with_range = [m for m in items if m.ref_low is not None]
        without = [m for m in items if m.ref_low is None]
        if with_range and without:
            flags.append(Flag(
                flag_id=_fid("range", analyte),
                kind=FlagKind.MISSING_RANGE,
                severity=FlagSeverity.FORMATTING,
                title=f"{display_for(analyte)} is missing a reference range in at least one document",
                reason=(
                    f"{_label(case, with_range[0])} prints a reference range "
                    f"({with_range[0].ref_text}), but {_label(case, without[0])} prints none. "
                    f"Reference ranges differ between laboratories, so a value without one "
                    f"cannot be judged normal or abnormal from this record."
                ),
                needs_clarification="Request the issuing laboratory's reference range for this result.",
                evidence_ids=[with_range[0].fact_id, without[0].fact_id],
            ))
    return flags


def check_missing_dates(case: Case) -> list[Flag]:
    flags: list[Flag] = []
    for d in case.documents:
        if d.doc_date is None and d.text.strip():
            flags.append(Flag(
                flag_id=_fid("nodate", d.doc_id),
                kind=FlagKind.MISSING_DATE,
                severity=FlagSeverity.FORMATTING,
                title=f"No date could be read from {d.filename}",
                reason=("No collection, report or visit date was found in this document, so its "
                        "contents cannot be positioned on the timeline."),
                needs_clarification="Confirm the date this document was issued.",
                evidence_ids=[],
            ))
        elif d.doc_date is not None and not d.date_is_explicit:
            flags.append(Flag(
                flag_id=_fid("impdate", d.doc_id),
                kind=FlagKind.DATE_CONFLICT,
                severity=FlagSeverity.FORMATTING,
                title=f"Date for {d.filename} is unlabelled",
                reason=(f"CAREGRAPH read {d.doc_date.isoformat()} from the top of this document, "
                        f"but it is not labelled as a collection or report date."),
                needs_clarification="Confirm what this date refers to.",
                evidence_ids=[],
            ))
    return flags


def check_statement_conflicts(case: Case) -> list[Flag]:
    """Medications present in one document and explicitly negated in another."""
    flags: list[Flag] = []
    meds: dict[str, list] = {}
    for s in case.statements:
        if s.category == "medication" and s.subject:
            meds.setdefault(s.subject, []).append(s)

    for subject, items in meds.items():
        affirmed = [s for s in items if not _NEGATION.search(s.text)]
        negated = [s for s in items if _NEGATION.search(s.text)]
        if affirmed and negated:
            flags.append(Flag(
                flag_id=_fid("stmt", subject),
                kind=FlagKind.STATEMENT_CONFLICT,
                severity=FlagSeverity.POSSIBLE,
                title=f"Conflicting records about {subject.title()}",
                reason=(f"One document records '{affirmed[0].text}' while another records "
                        f"'{negated[0].text}'. These cannot both describe the current state."),
                needs_clarification="Confirm the current medication list with the prescriber.",
                evidence_ids=[affirmed[0].fact_id, negated[0].fact_id],
            ))

        # same drug, different strength, across documents
        doses: dict[str, list] = {}
        for s in items:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu)\b", s.text, re.I)
            if m:
                doses.setdefault(f"{m[1]}{m[2].lower()}", []).append(s)
        if len(doses) > 1:
            keys = sorted(doses)
            a, b = doses[keys[0]][0], doses[keys[1]][0]
            if a.provenance.doc_id != b.provenance.doc_id:
                flags.append(Flag(
                    flag_id=_fid("dose", subject),
                    kind=FlagKind.VALUE_CONFLICT,
                    severity=FlagSeverity.POSSIBLE,
                    title=f"{subject.title()} appears at two different strengths",
                    reason=(f"{_fmt(case, a)} records '{a.text}' and {_fmt(case, b)} records "
                            f"'{b.text}'. This may be an intended change over time or a "
                            f"transcription error; the documents alone do not say which."),
                    needs_clarification="Confirm the current dose and when it was changed.",
                    evidence_ids=[a.fact_id, b.fact_id],
                ))
    return flags


def _fmt(case: Case, s) -> str:
    doc = case.doc(s.provenance.doc_id)
    return f"{doc.filename if doc else s.provenance.doc_id} p{s.provenance.page}"


ALL_CHECKS = (
    check_unit_mismatch,
    check_same_day_conflicts,
    check_context_incomparable,
    check_missing_ranges,
    check_missing_dates,
    check_statement_conflicts,
)


def run_all(case: Case) -> list[Flag]:
    flags: list[Flag] = []
    seen: set[str] = set()
    for check in ALL_CHECKS:
        for flag in check(case):
            if flag.flag_id not in seen:
                seen.add(flag.flag_id)
                flags.append(flag)
    order = {FlagSeverity.POSSIBLE: 0, FlagSeverity.FORMATTING: 1}
    flags.sort(key=lambda f: (order[f.severity], f.kind.value))
    return flags
