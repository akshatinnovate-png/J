import datetime as _dt

from caregraph.analysis import analyse
from caregraph.contradictions import run_all
from caregraph.extraction import ingest
from caregraph.schemas import Case, FlagKind, FlagSeverity


def case_from(*texts: str) -> Case:
    case = Case()
    for i, text in enumerate(texts):
        doc, m, s, img = ingest(f"doc{i}.txt", text=text)
        case.imaging.extend(img)
        case.documents.append(doc)
        case.measurements.extend(m)
        case.statements.extend(s)
    return case


def kinds(flags) -> set:
    return {f.kind for f in flags}


def test_incompatible_units_flagged_and_not_converted():
    case = case_from(
        "Collection date: 2024-01-10\nHbA1c: 6.4 % (ref 4.0-5.6)",
        "Collection date: 2024-06-10\nHbA1c: 53 mmol/mol",
    )
    flags = run_all(case)
    unit = [f for f in flags if f.kind is FlagKind.UNIT_MISMATCH]
    assert unit and "NOT plotted together" in unit[0].reason


def test_convertible_units_flagged_as_formatting_only():
    case = case_from(
        "Collection date: 2024-01-10\nLDL cholesterol 138 mg/dL",
        "Collection date: 2024-06-10\nLDL cholesterol 3.4 mmol/L",
    )
    unit = [f for f in run_all(case) if f.kind is FlagKind.UNIT_MISMATCH]
    assert unit and unit[0].severity is FlagSeverity.FORMATTING
    assert "standard conversion exists" in unit[0].reason


def test_same_day_conflicting_values_flagged_as_possible_contradiction():
    case = case_from(
        "Collection date: 2025-01-20\nFasting glucose 131 mg/dL",
        "Collection date: 2025-01-20\nFasting glucose 154 mg/dL",
    )
    conflicts = [f for f in run_all(case) if f.kind is FlagKind.VALUE_CONFLICT]
    assert conflicts
    assert conflicts[0].severity is FlagSeverity.POSSIBLE
    assert len(conflicts[0].evidence_ids) == 2


def test_system_never_decides_which_record_is_correct():
    case = case_from(
        "Collection date: 2025-01-20\nFasting glucose 131 mg/dL",
        "Collection date: 2025-01-20\nFasting glucose 154 mg/dL",
    )
    conflict = next(f for f in run_all(case) if f.kind is FlagKind.VALUE_CONFLICT)
    assert "cannot determine which record is correct" in conflict.reason
    assert conflict.needs_clarification


def test_same_day_values_within_tolerance_not_flagged():
    case = case_from(
        "Collection date: 2025-01-20\nFasting glucose 140 mg/dL",
        "Collection date: 2025-01-20\nFasting glucose 141 mg/dL",
    )
    assert not [f for f in run_all(case) if f.kind is FlagKind.VALUE_CONFLICT]


def test_missing_reference_range_flagged():
    case = case_from(
        "Collection date: 2024-01-10\nCreatinine 0.9 mg/dL (ref 0.6-1.3)",
        "Collection date: 2024-06-10\nCreatinine 1.1 mg/dL",
    )
    assert FlagKind.MISSING_RANGE in kinds(run_all(case))


def test_missing_date_flagged():
    case = case_from("HbA1c: 6.4 % (ref 4.0-5.6)\nNo date in this document at all.")
    assert FlagKind.MISSING_DATE in kinds(run_all(case))


def test_medication_dose_change_flagged_without_assuming_error():
    case = case_from(
        "Collection date: 2024-01-10\nMetformin 500 mg twice daily",
        "Collection date: 2024-06-10\nMetformin 1000 mg twice daily",
    )
    dose = [f for f in run_all(case) if "strength" in f.title]
    assert dose and "the documents alone do not say which" in dose[0].reason


def test_every_flag_names_evidence_or_a_document():
    from caregraph.samples import load_sample_case
    case = load_sample_case()
    for flag in case.flags:
        assert flag.reason and flag.needs_clarification
        if flag.kind not in (FlagKind.MISSING_DATE, FlagKind.DATE_CONFLICT):
            assert flag.evidence_ids, f"{flag.kind} should cite evidence"
        for fid in flag.evidence_ids:
            assert case.fact(fid) is not None


def test_no_duplicate_flag_ids():
    from caregraph.samples import load_sample_case
    case = load_sample_case()
    ids = [f.flag_id for f in case.flags]
    assert len(ids) == len(set(ids))


def test_single_clean_document_produces_no_contradictions():
    case = case_from("Collection date: 2025-01-20\nHbA1c: 5.2 % (ref 4.0-5.6)")
    assert run_all(case) == []
