"""Time-aligned series. Only genuinely comparable measurements are plotted."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from .schemas import Case, Measurement
from .units import PREFERRED_UNIT, convert, display_for


@dataclass
class SeriesPoint:
    date: _dt.date
    value: float              # value in the series unit
    original_value: float
    original_unit: str | None
    converted: bool
    fact_id: str
    doc_id: str
    raw_text: str
    context: str | None
    ref_low: float | None
    ref_high: float | None


@dataclass
class Series:
    analyte: str
    label: str
    unit: str | None
    points: list[SeriesPoint] = field(default_factory=list)
    excluded: list[tuple[Measurement, str]] = field(default_factory=list)

    @property
    def plottable(self) -> bool:
        return len(self.points) >= 1

    def change_summary(self) -> str | None:
        """Describe the recorded change only. No clinical interpretation."""
        if len(self.points) < 2:
            return None
        pts = sorted(self.points, key=lambda p: p.date)
        first, last = pts[0], pts[-1]
        delta = last.value - first.value
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "was unchanged"
        return (
            f"Recorded {self.label} {direction} from {first.value:g} to {last.value:g} "
            f"{self.unit or ''} between {first.date.isoformat()} and {last.date.isoformat()}."
        ).replace("  ", " ")


def build_series(case: Case) -> list[Series]:
    """Group measurements into comparable series, excluding what cannot be compared."""
    by_analyte: dict[str, list[Measurement]] = {}
    for m in case.measurements:
        by_analyte.setdefault(m.analyte, []).append(m)

    out: list[Series] = []
    for analyte, items in sorted(by_analyte.items()):
        # the series unit is the preferred unit if defined, else the most common printed unit
        units = [m.unit_canonical for m in items if m.unit_canonical]
        target = PREFERRED_UNIT.get(analyte)
        if target is None:
            target = max(set(units), key=units.count) if units else None

        series = Series(analyte=analyte, label=display_for(analyte), unit=target)
        contexts = {m.context for m in items if m.context}

        for m in items:
            if m.observed_on is None:
                series.excluded.append((m, "no date is recorded for this measurement"))
                continue
            if m.unit_canonical is None:
                series.excluded.append((m, "no unit is printed, so the value cannot be placed on a scale"))
                continue
            value = convert(analyte, m.value, m.unit_canonical, target) if target else None
            if value is None:
                series.excluded.append((
                    m, f"unit '{m.unit_canonical}' has no safe conversion to '{target}' "
                       f"for {display_for(analyte)}"))
                continue
            # a fasting and a random sample are not the same quantity
            if len(contexts) > 1 and m.context is None:
                series.excluded.append((
                    m, "other readings specify a sampling context and this one does not, "
                       "so it cannot be compared safely"))
                continue
            series.points.append(SeriesPoint(
                date=m.observed_on, value=round(value, 4), original_value=m.value,
                original_unit=m.unit_canonical, converted=(m.unit_canonical != target),
                fact_id=m.fact_id, doc_id=m.provenance.doc_id,
                raw_text=m.provenance.raw_text, context=m.context,
                ref_low=m.ref_low, ref_high=m.ref_high,
            ))
        series.points.sort(key=lambda p: p.date)
        out.append(series)
    return out


def document_events(case: Case) -> list[dict]:
    """Documents as timeline events, undated ones explicitly marked."""
    events = []
    for d in case.documents:
        events.append({
            "doc_id": d.doc_id,
            "label": d.doc_type or "Untyped document",
            "filename": d.filename,
            "date": d.doc_date,
            "dated": d.doc_date is not None,
            "explicit": d.date_is_explicit,
            "n_measurements": sum(1 for m in case.measurements if m.provenance.doc_id == d.doc_id),
            "n_statements": sum(1 for s in case.statements if s.provenance.doc_id == d.doc_id),
        })
    events.sort(key=lambda e: (e["date"] is None, e["date"] or _dt.date.min))
    return events
