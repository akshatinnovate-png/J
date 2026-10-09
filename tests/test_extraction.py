import datetime as _dt

import pytest

from caregraph.extraction import MAX_BYTES, ingest, pdf_to_text
from caregraph.schemas import Case

LAB = """LABORATORY REPORT
Collection date: 14/03/2025
HbA1c: 7.2 % (ref 4.0-5.6)
Fasting glucose 142 mg/dL [70-99]
Blood pressure 138/86 mmHg
Metformin 500 mg twice daily
"""


def test_extracts_measurements_with_units_and_ranges():
    doc, measurements, _, _i = ingest("lab.txt", text=LAB)
    by = {m.analyte: m for m in measurements}
    assert by["hba1c"].value == 7.2 and by["hba1c"].unit == "%"
    assert by["hba1c"].ref_low == 4.0 and by["hba1c"].ref_high == 5.6
    assert by["glucose_fasting"].value == 142
    assert by["bp_systolic"].value == 138 and by["bp_diastolic"].value == 86
    assert doc.doc_date == _dt.date(2025, 3, 14) and doc.date_is_explicit


def test_provenance_is_verbatim():
    _, measurements, _, _i = ingest("lab.txt", text=LAB)
    hba1c = next(m for m in measurements if m.analyte == "hba1c")
    assert hba1c.provenance.raw_text == "HbA1c: 7.2 % (ref 4.0-5.6)"
    assert hba1c.provenance.line == 3 and hba1c.provenance.doc_id


def test_medication_statement_extracted():
    _, _, statements, _i = ingest("lab.txt", text=LAB)
    meds = [s for s in statements if s.category == "medication"]
    assert meds and meds[0].subject == "metformin"


def test_missing_date_is_none_not_guessed():
    doc, _, _, _i = ingest("x.txt", text="HbA1c: 6.1 %\nNo dates here.")
    assert doc.doc_date is None


def test_unlabelled_date_is_marked_inexplicit():
    doc, _, _, _i = ingest("x.txt", text="2025-02-02\nHbA1c: 6.1 %")
    assert doc.doc_date == _dt.date(2025, 2, 2) and doc.date_is_explicit is False


def test_empty_input():
    doc, measurements, statements, _i = ingest("empty.txt", text="")
    assert measurements == [] and statements == [] and doc.doc_date is None


def test_malformed_pdf_reports_error_not_crash():
    doc, measurements, _, _i = ingest("broken.pdf", data=b"%PDF-1.4\nnot really a pdf")
    assert doc.extraction_error and measurements == []
    assert "paste the text" in doc.extraction_error.lower()


def test_pdf_to_text_on_garbage_is_safe():
    text, pages, error = pdf_to_text(b"%PDF-garbage")
    assert text == "" and error


def test_oversized_file_rejected():
    doc, measurements, _, _i = ingest("big.txt", data=b"x" * (MAX_BYTES + 1))
    assert "exceeds" in (doc.extraction_error or "") and measurements == []


def test_large_but_allowed_input_completes():
    text = "HbA1c: 6.5 %\n" + ("filler line that is not a measurement\n" * 5000)
    _, measurements, _, _i = ingest("big.txt", text=text)
    assert len(measurements) == 1


def test_non_utf8_bytes_do_not_crash():
    doc, _, _, _i = ingest("bin.txt", data=b"\xff\xfe\x00HbA1c: 6.5 %")
    assert doc.extraction_error is None or isinstance(doc.extraction_error, str)


def test_ingest_requires_data_or_text():
    with pytest.raises(ValueError):
        ingest("x.txt")


def test_values_without_known_analyte_are_ignored():
    _, measurements, _, _i = ingest("x.txt", text="Room number 214\nInvoice total 1500 INR")
    assert measurements == []


def test_date_of_birth_is_never_the_document_date():
    """Every real report carries a DOB above the collection date. Picking it
    would mis-position every fact in the document."""
    doc, _, _, _i = ingest("lab.txt", text=(
        "APEX DIAGNOSTICS\nName: R. Mehta\nDate of birth 04/11/1979\n"
        "Collection date: 14/01/2025\nHbA1c 7.8 % (ref 4.0-5.6)\n"))
    assert doc.doc_date == _dt.date(2025, 1, 14) and doc.date_is_explicit


def test_collection_date_beats_release_date():
    doc, _, _, _i = ingest("lab.txt", text=(
        "Report released: 15/01/2025\nCollection date: 14/01/2025\nHbA1c 7.8 %\n"))
    assert doc.doc_date == _dt.date(2025, 1, 14)


def test_document_with_only_a_dob_has_no_date():
    doc, _, _, _i = ingest("x.txt", text="Name: R. Mehta\nDOB: 04/11/1979\nHbA1c 7.8 %\n")
    assert doc.doc_date is None
