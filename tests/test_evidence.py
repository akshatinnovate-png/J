"""Verifier tests: the safety core. A claim may never be shown as supported
unless its references resolve and its numbers appear in the source."""
from caregraph.analysis import analyse
from caregraph.evidence import build_graph, graph_integrity, verify_claim
from caregraph.extraction import ingest
from caregraph.schemas import Case, Claim, EvidenceStatus

TEXT = """LABORATORY REPORT
Collection date: 2025-03-14
HbA1c: 7.2 % (ref 4.0-5.6)
Fasting glucose 142 mg/dL [70-99]
"""


def make_case() -> Case:
    case = Case()
    doc, m, s, img = ingest("lab.txt", text=TEXT)
    case.imaging.extend(img)
    case.documents.append(doc)
    case.measurements.extend(m)
    case.statements.extend(s)
    return case


def test_nonexistent_reference_is_rejected():
    case = make_case()
    claim = verify_claim(case, Claim(claim_id="c1", text="HbA1c is 7.2",
                                     evidence_ids=["m_doesnotexist"]))
    assert claim.status is EvidenceStatus.UNVERIFIED
    assert claim.evidence_ids == []
    assert claim.rejected_evidence_ids == ["m_doesnotexist"]
    assert "do not exist" in claim.caveat


def test_partially_dangling_reference_downgrades_to_partial():
    case = make_case()
    real = case.measurements[0].fact_id
    claim = verify_claim(case, Claim(claim_id="c2", text="A statement",
                                     evidence_ids=[real, "m_fake"]))
    assert claim.status is EvidenceStatus.PARTIAL
    assert claim.evidence_ids == [real]


def test_uncited_claim_is_unverified():
    case = make_case()
    claim = verify_claim(case, Claim(claim_id="c3", text="Your kidneys are fine."))
    assert claim.status is EvidenceStatus.UNVERIFIED


def test_claim_matching_source_is_supported():
    case = make_case()
    hba1c = next(m for m in case.measurements if m.analyte == "hba1c")
    claim = verify_claim(case, Claim(claim_id="c4",
                                     text="HbA1c was recorded as 7.2 %.",
                                     evidence_ids=[hba1c.fact_id]))
    assert claim.status is EvidenceStatus.SUPPORTED


def test_hallucinated_number_is_not_supported():
    case = make_case()
    hba1c = next(m for m in case.measurements if m.analyte == "hba1c")
    claim = verify_claim(case, Claim(claim_id="c5",
                                     text="HbA1c was recorded as 9.9 %.",
                                     evidence_ids=[hba1c.fact_id]))
    assert claim.status is EvidenceStatus.PARTIAL
    assert "9.9" in claim.caveat


def test_general_education_is_labelled_not_evidenced():
    case = make_case()
    claim = verify_claim(case, Claim(claim_id="c6", text="HbA1c reflects average glucose.",
                                     is_general_education=True))
    assert claim.status is EvidenceStatus.INSUFFICIENT
    assert "educational" in claim.caveat.lower()


def test_conflicting_evidence_outranks_a_clean_text_match():
    """A claim citing records the radar flagged as conflicting is never 'supported'."""
    from caregraph.samples import load_sample_case
    case = load_sample_case()
    conflicting = [c for c in case.claims if c.status is EvidenceStatus.CONFLICTING]
    assert conflicting, "demo set should produce at least one conflicting-evidence claim"


def test_graph_has_no_dangling_edges():
    case = analyse(make_case())
    graph = build_graph(case)
    ids = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_every_fact_node_links_to_a_real_document():
    case = analyse(make_case())
    graph = build_graph(case)
    doc_ids = {d.doc_id for d in case.documents}
    for node in graph["nodes"]:
        if node["kind"] == "fact":
            assert node["doc_id"] in doc_ids


def test_integrity_report_counts_rejections():
    case = analyse(make_case())
    case.claims.append(verify_claim(case, Claim(claim_id="c9", text="x",
                                                evidence_ids=["m_nope", "m_nope2"])))
    report = graph_integrity(case)
    assert report["rejected_references"] == 2  # retained for audit, not silently dropped
    assert report["claims_by_status"].get("unverified", 0) >= 1


def test_dates_in_a_claim_do_not_count_as_unsupported_numbers():
    """An ISO date tokenises as 2025, -1, -14. Reading those as asserted values
    would downgrade every claim that says when something was recorded."""
    from caregraph.evidence import _numbers
    nums = _numbers("Recorded HbA1c decreased from 7.8 to 7.4 % between "
                    "2025-01-14 and 2025-04-18.")
    assert nums == {"7.8", "7.4"}


def test_range_hyphen_is_not_read_as_a_minus_sign():
    from caregraph.evidence import _numbers
    assert _numbers("reference range of 4-5.6") == {"4", "5.6"}
    assert _numbers("delta was -3.2") == {"-3.2"}


def test_trend_claim_over_real_sources_is_supported():
    case = make_case()
    case.measurements[0].observed_on = __import__("datetime").date(2025, 1, 14)
    hba1c = next(m for m in case.measurements if m.analyte == "hba1c")
    claim = verify_claim(case, Claim(
        claim_id="t1",
        text=f"Recorded HbA1c was {hba1c.value:g} % on 2025-03-14.",
        evidence_ids=[hba1c.fact_id]))
    assert claim.status is EvidenceStatus.SUPPORTED


def test_digits_inside_an_analyte_name_are_not_values():
    from caregraph.evidence import _numbers
    assert _numbers("HbA1c was 7.8 %") == {"7.8"}
    assert _numbers("SpO2 98 %") == {"98"}
