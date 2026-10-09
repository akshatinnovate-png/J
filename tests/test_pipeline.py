"""End-to-end tests over the synthetic demo set and the timeline engine."""
import datetime as _dt

from caregraph.analysis import analyse, appointment_brief, explain_facts
from caregraph.evidence import build_graph, graph_integrity
from caregraph.extraction import ingest
from caregraph.samples import load_sample_case, sample_files
from caregraph.schemas import Case, EvidenceStatus, FlagKind, FlagSeverity
from caregraph.timeline import build_series, document_events


def test_demo_set_ingests_four_documents():
    case = load_sample_case()
    assert len(case.documents) == 4
    assert all(d.is_synthetic for d in case.documents)
    assert all(d.extraction_error is None for d in case.documents)


def test_demo_set_is_not_hardcoded():
    """The pipeline must derive findings from the files, not from a fixture.

    Editing a sample value must change the output; if the answers were
    hardcoded, these two runs would be identical.
    """
    baseline = load_sample_case()
    base_flags = {f.flag_id for f in baseline.flags}

    case = Case()
    for path in sample_files():
        text = path.read_text(encoding="utf-8")
        if "Fasting glucose 154 mg/dL" in text:
            text = text.replace("Fasting glucose 154 mg/dL", "Fasting glucose 131 mg/dL")
        doc, m, s = ingest(path.name, text=text, is_synthetic=True)
        case.documents.append(doc)
        case.measurements.extend(m)
        case.statements.extend(s)
    modified = analyse(case)

    assert {f.flag_id for f in modified.flags} != base_flags
    # the same-day glucose conflict must disappear once the values agree
    assert not [f for f in modified.flags
                if f.kind is FlagKind.VALUE_CONFLICT and "glucose" in f.title.lower()]


def test_demo_set_finds_the_planted_same_day_conflict():
    case = load_sample_case()
    conflicts = [f for f in case.flags if f.kind is FlagKind.VALUE_CONFLICT]
    assert any("glucose" in f.title.lower() for f in conflicts)


def test_demo_set_finds_the_planted_injection():
    case = load_sample_case()
    injected = [d for d in case.documents if d.injection_findings]
    assert len(injected) == 1
    # and the injection did not suppress flagging, which is what it asked for
    assert case.flags


def test_non_convertible_units_are_excluded_from_the_chart():
    """HbA1c in mmol/mol must never be plotted on a % axis."""
    case = load_sample_case()
    hba1c = next(s for s in build_series(case) if s.analyte == "hba1c")
    assert hba1c.unit == "%"
    assert all(p.original_unit == "%" for p in hba1c.points)
    excluded_units = {m.unit_canonical for m, _ in hba1c.excluded}
    assert "mmol/mol" in excluded_units


def test_convertible_units_are_plotted_with_the_original_preserved():
    case = load_sample_case()
    ldl = next(s for s in build_series(case) if s.analyte == "ldl")
    converted = [p for p in ldl.points if p.converted]
    assert converted
    point = converted[0]
    assert point.original_unit == "mmol/L" and point.original_value == 3.4
    assert 130 < point.value < 133  # 3.4 mmol/L in mg/dL


def test_measurements_without_a_date_are_excluded_not_guessed():
    case = Case()
    doc, m, s = ingest("nodate.txt", text="HbA1c: 6.1 %")
    case.documents.append(doc)
    case.measurements.extend(m)
    series = build_series(analyse(case))
    hba1c = next(x for x in series if x.analyte == "hba1c")
    assert hba1c.points == [] and len(hba1c.excluded) == 1
    assert "no date" in hba1c.excluded[0][1]


def test_missing_data_is_not_treated_as_zero():
    case = load_sample_case()
    for series in build_series(case):
        for point in series.points:
            assert point.original_unit is not None
            assert point.date is not None
    assert not any(p.value == 0 and p.original_value != 0
                   for s in build_series(case) for p in s.points)


def test_undated_documents_are_not_positioned_on_the_timeline():
    case = Case()
    doc, m, s = ingest("nodate.txt", text="HbA1c: 6.1 %")
    case.documents.append(doc)
    events = document_events(analyse(case))
    assert events[0]["dated"] is False and events[0]["date"] is None


def test_change_summary_describes_numbers_without_interpreting_them():
    case = load_sample_case()
    ldl = next(s for s in build_series(case) if s.analyte == "ldl")
    summary = ldl.change_summary()
    assert summary and "Recorded" in summary
    for forbidden in ("improve", "worse", "better", "healthy", "dangerous", "should"):
        assert forbidden not in summary.lower()


def test_every_claim_reference_resolves_to_a_real_fact():
    case = load_sample_case()
    known = case.fact_ids()
    for claim in case.claims:
        for fid in claim.evidence_ids:
            assert fid in known


def test_no_claim_is_supported_without_evidence():
    case = load_sample_case()
    for claim in case.claims:
        if claim.status is EvidenceStatus.SUPPORTED:
            assert claim.evidence_ids


def test_questions_are_prioritised_and_anchored():
    case = load_sample_case()
    assert case.questions
    assert case.questions[0].priority <= case.questions[-1].priority
    known = case.fact_ids()
    for question in case.questions:
        for fid in question.evidence_ids:
            assert fid in known


def test_gaps_report_absence_without_inventing_content():
    case = load_sample_case()
    assert case.gaps
    labels = " ".join(g.label.lower() for g in case.gaps)
    assert "reference range" in labels or "date" in labels


def test_brief_carries_disclaimer_and_simulated_marking():
    brief = appointment_brief(load_sample_case())
    assert "does not diagnose" in brief
    assert "SIMULATED DATA" in brief
    assert "Unresolved inconsistencies" in brief and "Questions to ask" in brief


def test_brief_never_states_a_diagnosis_or_treatment_change():
    brief = appointment_brief(load_sample_case()).lower()
    for forbidden in ("you have diabetes", "you should stop taking",
                      "increase your dose", "i diagnose"):
        assert forbidden not in brief


def test_explain_facts_returns_a_verified_claim():
    case = load_sample_case()
    fact_id = case.measurements[0].fact_id
    claim, result = explain_facts(case, [fact_id], force_offline=True)
    assert claim.evidence_ids == [fact_id]
    assert claim.status in (EvidenceStatus.SUPPORTED, EvidenceStatus.PARTIAL,
                            EvidenceStatus.CONFLICTING)
    assert result.simulated


def test_explain_facts_with_unknown_id_produces_no_evidence():
    case = load_sample_case()
    claim, _ = explain_facts(case, ["m_nonexistent"], force_offline=True)
    assert claim.evidence_ids == []
    assert claim.status is EvidenceStatus.UNVERIFIED


def test_graph_is_connected_and_auditable():
    case = load_sample_case()
    graph = build_graph(case)
    assert len(graph["nodes"]) > 20 and graph["edges"]
    report = graph_integrity(case)
    assert report["rejected_references"] == 0
    assert report["documents"] == 4


def test_empty_case_analyses_without_error():
    case = analyse(Case())
    assert case.flags == [] and case.claims == []
    assert build_graph(case) == {"nodes": [], "edges": []}
    assert "Appointment preparation brief" in appointment_brief(case)


def test_pipeline_is_deterministic():
    a, b = load_sample_case(), load_sample_case()
    assert [f.flag_id for f in a.flags] == [f.flag_id for f in b.flags]
    assert [c.claim_id for c in a.claims] == [c.claim_id for c in b.claims]
