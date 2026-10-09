"""Manual record entry.

Typed entries go through exactly the same pipeline as an uploaded PDF: they are
rendered to document text, re-parsed by the extractor, and carry real provenance
pointing back at the line the user typed. Nothing is injected into the Case
behind the extractor's back, so a typed record is verified on the same terms.
"""
from __future__ import annotations

import datetime as _dt

from .analysis import analyse
from .extraction import ingest
from .imaging import MODALITIES
from .schemas import Case
from .units import ANALYTES, display_for

ENTRY_UNITS = {
    "hba1c": ["%", "mmol/mol"],
    "glucose_fasting": ["mg/dL", "mmol/L"],
    "glucose_random": ["mg/dL", "mmol/L"],
    "ldl": ["mg/dL", "mmol/L"],
    "hdl": ["mg/dL", "mmol/L"],
    "total_cholesterol": ["mg/dL", "mmol/L"],
    "triglycerides": ["mg/dL", "mmol/L"],
    "creatinine": ["mg/dL", "umol/L"],
    "egfr": ["mL/min/1.73m2"],
    "haemoglobin": ["g/dL", "g/L"],
    "tsh": ["mIU/L"],
    "vitamin_d": ["ng/mL", "nmol/L"],
    "alt": ["U/L"],
    "weight": ["kg", "lb"],
    "bmi": ["kg/m2"],
}

ENTRY_ANALYTES = [k for k in ANALYTES if k not in ("bp_systolic", "bp_diastolic")]


def compose_document(title: str, doc_date: _dt.date, lines: list[str]) -> str:
    """Render typed entries as a report, which the extractor then parses."""
    header = [title.upper(), f"Collection date: {doc_date.isoformat()}", ""]
    return "\n".join(header + lines) + "\n"


def measurement_line(analyte: str, value: float, unit: str,
                     ref_low: float | None = None, ref_high: float | None = None,
                     context: str | None = None) -> str:
    line = f"{display_for(analyte)} {value:g} {unit}"
    if ref_low is not None and ref_high is not None:
        line += f" (ref {ref_low:g}-{ref_high:g})"
    if context:
        line += f"  [{context}]"
    return line


def bp_line(systolic: float, diastolic: float) -> str:
    return f"Blood pressure {systolic:g}/{diastolic:g} mmHg"


def medication_line(name: str, dose: str, frequency: str) -> str:
    return f"{name.strip().title()} {dose.strip()} {frequency.strip()}".strip()


def imaging_line(modality: str, body_part: str, finding: str) -> str:
    noun = {
        "xray_chest": "Chest X-ray",
        "mri_brain": "MRI",
        "ct_abdomen": "CT",
        "ultrasound_cardiac": "Ultrasound",
        "ecg": "ECG",
    }.get(modality, MODALITIES.get(modality, modality))
    part = f" {body_part.strip()}" if body_part.strip() else ""
    tail = f": {finding.strip()}" if finding.strip() else ""
    return f"{noun}{part}{tail}"


def note_line(kind: str, text: str) -> str:
    prefix = {"observation": "Patient reports", "instruction": "Advised",
              "allergy": "Allergy"}.get(kind, "")
    text = text.strip().rstrip(".")
    return f"{prefix} {text}." if prefix else f"{text}."


def add_document(case: Case, filename: str, text: str, is_synthetic: bool = True) -> Case:
    """Ingest composed text into an existing case and re-run the full analysis."""
    doc, measurements, statements, imaging = ingest(
        filename, text=text, is_synthetic=is_synthetic)
    case.documents.append(doc)
    case.measurements.extend(measurements)
    case.statements.extend(statements)
    case.imaging.extend(imaging)
    return analyse(case)


def preview_counts(text: str) -> dict[str, int]:
    """What the extractor would find, so the form can show it before committing."""
    _doc, measurements, statements, imaging = ingest("preview.txt", text=text)
    return {
        "measurements": len(measurements),
        "statements": len(statements),
        "imaging": len(imaging),
    }
