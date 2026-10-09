"""Synthetic demo records.

These files are fabricated and contain deliberate documentation inconsistencies.
They exist so the pipeline can be demonstrated without any real patient data.
Expected answers are NOT hardcoded anywhere - the pipeline processes these files
exactly as it processes an upload.
"""
from __future__ import annotations

from pathlib import Path

SAMPLE_DIR = Path(__file__).parent


def sample_files() -> list[Path]:
    return sorted(SAMPLE_DIR.glob("report_*.txt"))


def load_sample_case():
    """Ingest and analyse the synthetic demo set."""
    from ..analysis import analyse
    from ..extraction import ingest
    from ..schemas import Case

    case = Case()
    for path in sample_files():
        doc, measurements, statements = ingest(
            path.name, text=path.read_text(encoding="utf-8"), is_synthetic=True
        )
        case.documents.append(doc)
        case.measurements.extend(measurements)
        case.statements.extend(statements)
    return analyse(case)
