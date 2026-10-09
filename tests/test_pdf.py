"""The PDF path is exercised against a real, byte-level PDF file."""
from caregraph.extraction import ingest, pdf_to_text


def test_real_pdf_extracts_measurements(lab_pdf_bytes):
    doc, measurements, statements, _img = ingest("lab.pdf", data=lab_pdf_bytes)
    assert doc.extraction_error is None, doc.extraction_error
    by = {m.analyte: m for m in measurements}
    assert by["hba1c"].value == 7.2
    assert by["glucose_fasting"].value == 142
    assert doc.doc_date is not None and doc.doc_type == "Laboratory Report"
    assert any(s.category == "medication" for s in statements)


def test_pdf_provenance_records_a_page(lab_pdf_bytes):
    _, measurements, _, _img = ingest("lab.pdf", data=lab_pdf_bytes)
    assert all(m.provenance.page >= 1 for m in measurements)
    assert all(m.provenance.raw_text.strip() for m in measurements)


def test_pdf_with_no_text_layer_explains_the_failure(make_pdf):
    empty = make_pdf([])
    text, _pages, error = pdf_to_text(empty)
    assert text.strip() == ""
    assert error and "scanned" in error.lower()


def test_truncated_pdf_does_not_crash(lab_pdf_bytes):
    doc, measurements, _, _img = ingest("cut.pdf", data=lab_pdf_bytes[: len(lab_pdf_bytes) // 2])
    assert measurements == [] or doc.extraction_error
