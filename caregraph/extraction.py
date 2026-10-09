"""Document ingestion: PDF/text -> Document + Measurement + Statement.

Every extracted item carries verbatim provenance. Nothing here infers a value,
a date or a unit that is not literally printed in the source.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import re

from . import safety
from .schemas import Document, Measurement, Provenance, Statement
from .units import analyte_key, canonical_unit, display_for

MAX_BYTES = 10 * 1024 * 1024  # refuse absurd inputs rather than hang the UI

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"), "dMy"),
    (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"), "Mdy"),
]

_DATE_LABEL = re.compile(
    r"(?i)\b(report|collection|collected|specimen|visit|consultation|sample|test|issued|date)\b[^\n]{0,30}?"
    r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
)

_DOC_TYPES: list[tuple[str, str]] = [
    ("discharge summary", "Discharge Summary"),
    ("laboratory report", "Laboratory Report"),
    ("lab report", "Laboratory Report"),
    ("pathology report", "Laboratory Report"),
    ("blood test", "Laboratory Report"),
    ("consultation note", "Consultation Note"),
    ("clinic note", "Consultation Note"),
    ("prescription", "Prescription"),
    ("radiology report", "Radiology Report"),
    ("imaging report", "Radiology Report"),
    ("referral letter", "Referral Letter"),
]

# value + optional unit, with an optional bracketed reference range after it
_NUM = r"(-?\d+(?:\.\d+)?)"
_UNIT = r"([A-Za-zµ%][A-Za-z0-9µ%/\.\^²]*(?:\s?/\s?[A-Za-z0-9\.\^²]+)*)?"
_MEAS_RE = re.compile(
    rf"^\s*([A-Za-z][A-Za-z0-9 \-\(\)/']{{1,45}}?)\s*[:\-]?\s+{_NUM}\s*{_UNIT}\s*(.*)$"
)
_RANGE_RE = re.compile(
    rf"(?:ref(?:erence)?(?:\s*range)?\s*[:=]?\s*)?[\(\[]?\s*{_NUM}\s*(?:-|–|to)\s*{_NUM}\s*[\)\]]?"
)
_BP_RE = re.compile(r"(?i)\b(?:blood\s+pressure|bp)\b\s*[:\-]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mmhg)?")

_CONTEXT_WORDS = {
    "fasting": "fasting", "post-prandial": "post-prandial", "postprandial": "post-prandial",
    "random": "random", "non-fasting": "non-fasting", "seated": "seated", "standing": "standing",
}

_MED_RE = re.compile(
    r"(?i)^\s*(?:rx|medication|med|drug)?\s*[:\-]?\s*([A-Z][A-Za-z\-]{2,30})\s+"
    r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|iu))\b(.*)$"
)
_STATEMENT_HINTS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"(?i)\ballerg(y|ic|ies)\b"), "allergy", None),
    (re.compile(r"(?i)\b(advised|advise|recommend(ed)?|instruct(ed)?|should|follow[- ]up|review in)\b"), "instruction", None),
    (re.compile(r"(?i)\b(diagnos(is|ed)|impression|history of|known case of|patient reports?|complains? of|denies)\b"), "observation", None),
]


def _hash(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _parse_date(raw: str) -> _dt.date | None:
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(raw)
        if not m:
            continue
        try:
            if kind == "ymd":
                return _dt.date(int(m[1]), int(m[2]), int(m[3]))
            if kind == "dmy":
                return _dt.date(int(m[3]), int(m[2]), int(m[1]))
            if kind == "dMy":
                mon = _MONTHS.get(m[2][:3].lower())
                return _dt.date(int(m[3]), mon, int(m[1])) if mon else None
            if kind == "Mdy":
                mon = _MONTHS.get(m[1][:3].lower())
                return _dt.date(int(m[3]), mon, int(m[2])) if mon else None
        except ValueError:
            return None
    return None


def find_document_date(text: str) -> tuple[_dt.date | None, bool]:
    """Prefer a labelled date ('Collection date: ...'). Returns (date, explicit)."""
    m = _DATE_LABEL.search(text)
    if m:
        d = _parse_date(m[2])
        if d:
            return d, True
    d = _parse_date(text[:600])
    return (d, False) if d else (None, False)


def find_doc_type(text: str) -> str | None:
    low = text.lower()
    for needle, label in _DOC_TYPES:
        if needle in low:
            return label
    return None


def pdf_to_text(data: bytes) -> tuple[str, int, str | None]:
    """Return (text, page_count, error). Never raises on a malformed PDF."""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - optional dependency
        return "", 0, "pdfplumber is not installed; use the text-input fallback."
    try:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        text = "\n\f\n".join(pages)
        if not text.strip():
            return "", len(pages), (
                "No selectable text found. This looks like a scanned PDF; "
                "CAREGRAPH does not run OCR. Paste the text instead."
            )
        return text, len(pages), None
    except Exception as exc:  # malformed/encrypted PDF
        return "", 0, f"Could not read this PDF ({type(exc).__name__}). Paste the text instead."


def _context_for(line: str) -> str | None:
    low = line.lower()
    for word, label in _CONTEXT_WORDS.items():
        if word in low:
            return label
    return None


def _parse_range(tail: str) -> tuple[float | None, float | None, str | None]:
    m = _RANGE_RE.search(tail)
    if not m:
        return None, None, None
    try:
        ref_text = m.group(0).strip().strip("()[] ")
        return float(m[1]), float(m[2]), ref_text
    except ValueError:
        return None, None, None


def extract_facts(doc: Document) -> tuple[list[Measurement], list[Statement]]:
    """Pull measurements and statements out of a document's text."""
    measurements: list[Measurement] = []
    statements: list[Statement] = []
    page = 1
    offset = 0

    for line_no, line in enumerate(doc.text.splitlines(), start=1):
        if "\f" in line:
            page += line.count("\f")
        stripped = line.strip()
        line_start = offset
        offset += len(line) + 1
        if not stripped or len(stripped) > 400:
            continue
        # all-caps banner lines are headers, not clinical statements
        is_banner = stripped.isupper() and len(stripped.split()) <= 6

        prov = Provenance(
            doc_id=doc.doc_id, page=page, line=line_no,
            char_start=line_start, char_end=line_start + len(line), raw_text=stripped,
        )
        line_date = _parse_date(stripped) or doc.doc_date
        context = _context_for(stripped)
        matched_measurement = False

        # blood pressure is two analytes printed as one token
        bp = _BP_RE.search(stripped)
        if bp:
            for key, raw_val in (("bp_systolic", bp[1]), ("bp_diastolic", bp[2])):
                measurements.append(Measurement(
                    fact_id=f"m_{_hash(doc.doc_id, line_no, key)}",
                    analyte=key, display_name=display_for(key), value=float(raw_val),
                    unit=canonical_unit(bp[3]) if bp[3] else "mmHg",
                    unit_canonical=canonical_unit(bp[3]) if bp[3] else "mmHg",
                    observed_on=line_date, context=context, provenance=prov,
                ))
            matched_measurement = True

        if not matched_measurement:
            m = _MEAS_RE.match(stripped)
            if m:
                label, raw_value, raw_unit, tail = m[1], m[2], m[3], m[4] or ""
                key = analyte_key(label)
                if key:
                    # a bare trailing number is a range start, not a unit
                    unit = canonical_unit(raw_unit) if raw_unit and not raw_unit.isdigit() else None
                    lo, hi, ref_text = _parse_range(tail)
                    try:
                        value = float(raw_value)
                    except ValueError:
                        value = None
                    if value is not None:
                        measurements.append(Measurement(
                            fact_id=f"m_{_hash(doc.doc_id, line_no, key, raw_value)}",
                            analyte=key, display_name=label.strip(), value=value,
                            unit=unit, unit_canonical=unit,
                            ref_low=lo, ref_high=hi, ref_text=ref_text,
                            observed_on=line_date, context=context, provenance=prov,
                        ))
                        matched_measurement = True

        if matched_measurement:
            continue

        med = _MED_RE.match(stripped)
        if med and len(stripped) < 160:
            statements.append(Statement(
                fact_id=f"s_{_hash(doc.doc_id, line_no, 'med')}",
                category="medication", text=stripped,
                subject=med[1].lower(), observed_on=line_date, provenance=prov,
            ))
            continue

        for pattern, category, _ in _STATEMENT_HINTS:
            if not is_banner and pattern.search(stripped):
                statements.append(Statement(
                    fact_id=f"s_{_hash(doc.doc_id, line_no, category)}",
                    category=category, text=stripped,
                    subject=None, observed_on=line_date, provenance=prov,
                ))
                break

    return measurements, statements


def ingest(filename: str, data: bytes | None = None, text: str | None = None,
           is_synthetic: bool = False) -> tuple[Document, list[Measurement], list[Statement]]:
    """Ingest one document from PDF bytes or raw text."""
    doc_id = f"d_{_hash(filename, len(data or b''), (text or '')[:200])}"
    error: str | None = None
    pages = 1

    if text is None:
        if data is None:
            raise ValueError("ingest() needs either data or text")
        if len(data) > MAX_BYTES:
            error = f"File exceeds the {MAX_BYTES // (1024 * 1024)} MB limit and was not processed."
            text = ""
        elif data[:5] == b"%PDF-":
            text, pages, error = pdf_to_text(data)
        else:
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text, error = "", "File is not readable text or PDF."
    text = text or ""

    findings = safety.scan_for_injection(text)
    doc = Document(
        doc_id=doc_id, filename=filename, text=text, page_count=max(pages, 1),
        is_synthetic=is_synthetic, extraction_error=error, injection_findings=findings,
    )
    if text.strip():
        doc.doc_type = find_doc_type(text)
        doc.doc_date, doc.date_is_explicit = find_document_date(text)
        measurements, statements = extract_facts(doc)
    else:
        measurements, statements = [], []
    return doc, measurements, statements
