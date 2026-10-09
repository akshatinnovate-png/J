"""The care-flow canvas: a chronological, branching view of the whole record.

Events are laid out left-to-right in time and stacked into lanes so nothing
overlaps, then joined with bezier connectors. Imaging events carry a generated
thumbnail of the study. Every node is clickable and resolves to its source text.
"""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field

import plotly.graph_objects as go

from . import imaging
from . import ui_theme as T
from .schemas import Case, FlagSeverity
from .units import display_for

CATEGORIES = ["Docs", "Labs", "Imaging", "Medications", "Visits", "Findings"]


@dataclass
class FlowNode:
    node_id: str
    category: str
    title: str
    subtitle: str
    date: _dt.date | None
    doc_id: str
    fact_id: str | None = None
    modality: str | None = None
    value_text: str = ""
    lane: int = 0
    x: float = 0.0
    y: float = 0.0
    flagged: bool = False
    detail: str = ""


def build_nodes(case: Case, categories: list[str] | None = None) -> list[FlowNode]:
    """One node per meaningful record event, filtered by category."""
    wanted = set(categories or CATEGORIES)
    flagged_facts: set[str] = set()
    for f in case.flags:
        if f.severity is FlagSeverity.POSSIBLE:
            flagged_facts |= set(f.evidence_ids)

    nodes: list[FlowNode] = []

    if "Docs" in wanted:
        for d in case.documents:
            if not d.text.strip():
                continue
            nodes.append(FlowNode(
                node_id=d.doc_id, category="Docs",
                title=d.doc_type or "Document", subtitle=d.filename,
                date=d.doc_date, doc_id=d.doc_id,
                detail=f"{d.page_count} page(s)",
            ))

    if "Labs" in wanted:
        for m in case.measurements:
            if m.analyte in ("bp_systolic", "bp_diastolic") and "Visits" in wanted:
                continue
            unit = m.unit or ""
            nodes.append(FlowNode(
                node_id=m.fact_id, category="Labs",
                title=display_for(m.analyte),
                subtitle=f"{m.value:g} {unit}".strip(),
                date=m.observed_on, doc_id=m.provenance.doc_id, fact_id=m.fact_id,
                value_text=f"{m.value:g} {unit}".strip(),
                flagged=m.fact_id in flagged_facts,
                detail=m.provenance.raw_text,
            ))

    if "Imaging" in wanted:
        for r in case.imaging:
            nodes.append(FlowNode(
                node_id=r.fact_id, category="Imaging",
                title=imaging.MODALITIES.get(r.modality, r.modality).split("·")[0].strip(),
                subtitle=(r.body_part or "").title() or "Study",
                date=r.observed_on, doc_id=r.provenance.doc_id, fact_id=r.fact_id,
                modality=r.modality, flagged=r.fact_id in flagged_facts,
                detail=r.provenance.raw_text,
            ))

    if "Medications" in wanted:
        for s in case.statements:
            if s.category != "medication":
                continue
            nodes.append(FlowNode(
                node_id=s.fact_id, category="Medications",
                title=(s.subject or "Medication").title(),
                subtitle=s.text[:34], date=s.observed_on, doc_id=s.provenance.doc_id,
                fact_id=s.fact_id, flagged=s.fact_id in flagged_facts,
                detail=s.provenance.raw_text,
            ))

    if "Visits" in wanted:
        for m in case.measurements:
            if m.analyte != "bp_systolic":
                continue
            dia = next((d for d in case.measurements
                        if d.analyte == "bp_diastolic"
                        and d.provenance.line == m.provenance.line
                        and d.provenance.doc_id == m.provenance.doc_id), None)
            nodes.append(FlowNode(
                node_id=m.fact_id, category="Visits", title="Blood pressure",
                subtitle=f"{m.value:g}/{dia.value:g} mmHg" if dia else f"{m.value:g} mmHg",
                date=m.observed_on, doc_id=m.provenance.doc_id, fact_id=m.fact_id,
                flagged=m.fact_id in flagged_facts, detail=m.provenance.raw_text,
            ))

    if "Findings" in wanted:
        for s in case.statements:
            if s.category not in ("observation", "instruction", "allergy"):
                continue
            nodes.append(FlowNode(
                node_id=s.fact_id, category="Findings",
                title=s.category.title(), subtitle=s.text[:38],
                date=s.observed_on, doc_id=s.provenance.doc_id, fact_id=s.fact_id,
                flagged=s.fact_id in flagged_facts, detail=s.provenance.raw_text,
            ))

    return [n for n in nodes if n.date is not None]


def layout(nodes: list[FlowNode], max_per_column: int = 7) -> list[FlowNode]:
    """Cluster events into a column per date, stacked around the central spine.

    Records arrive in bursts - a visit produces a dozen entries on one day - so a
    column per date reads far better than one lane per collision.
    """
    nodes = sorted(nodes, key=lambda n: (n.date, n.category, n.title))
    if not nodes:
        return nodes

    first = min(n.date for n in nodes)
    last = max(n.date for n in nodes)
    span = max((last - first).days, 1)

    by_date: dict[_dt.date, list[FlowNode]] = {}
    for n in nodes:
        by_date.setdefault(n.date, []).append(n)

    # keep columns clear of each other even when two dates are close together
    dates = sorted(by_date)
    min_sep = 0.075
    xs: dict[_dt.date, float] = {}
    prev = -1.0
    for d in dates:
        x = (d - first).days / span
        if x - prev < min_sep:
            x = prev + min_sep
        xs[d] = x
        prev = x
    scale = max(max(xs.values()), 1e-6)
    if scale > 1.0:
        xs = {d: v / scale for d, v in xs.items()}

    step = 0.42
    for d, group in by_date.items():
        # order within a column: documents nearest the spine, detail further out
        order = {"Docs": 0, "Visits": 1, "Imaging": 2, "Labs": 3, "Medications": 4, "Findings": 5}
        group.sort(key=lambda n: (order.get(n.category, 9), n.title))
        for i, n in enumerate(group):
            col = i // max_per_column
            idx = i % max_per_column
            n.lane = idx
            offset = (idx + 2) // 2
            sign = 1 if idx % 2 == 0 else -1
            n.x = xs[d] + col * 0.062
            n.y = sign * offset * step
    return nodes


def _bezier(x0: float, y0: float, x1: float, y1: float, steps: int = 26):
    """Horizontal-tangent cubic bezier, which is what gives the flowing look."""
    cx = (x1 - x0) * 0.45
    xs, ys = [], []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        xs.append(mt ** 3 * x0 + 3 * mt ** 2 * t * (x0 + cx)
                  + 3 * mt * t ** 2 * (x1 - cx) + t ** 3 * x1)
        ys.append(mt ** 3 * y0 + 3 * mt ** 2 * t * y0
                  + 3 * mt * t ** 2 * y1 + t ** 3 * y1)
    return xs, ys


def _label_for(n: FlowNode, label_all: bool) -> str:
    if label_all or n.category in ("Docs", "Imaging") or n.flagged:
        return n.title
    return ""


def figure(case: Case, nodes: list[FlowNode], focus: str | None = None,
           show_thumbnails: bool = True) -> go.Figure:
    fig = go.Figure()
    if not nodes:
        fig.add_annotation(text="No dated events match these filters",
                           showarrow=False, font=dict(color=T.MUTED, size=14))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        fig.update_layout(height=430, paper_bgcolor=T.CANVAS, plot_bgcolor=T.CANVAS)
        return fig

    first = min(n.date for n in nodes)
    last = max(n.date for n in nodes)
    span = max((last - first).days, 1)

    # month gridlines
    month = _dt.date(first.year, first.month, 1)
    while month <= last:
        mx = (month - first).days / span
        if 0 <= mx <= 1:
            fig.add_shape(type="line", x0=mx, x1=mx, y0=-1.25, y1=1.25,
                          line=dict(color=T.BORDER, width=1, dash="dot"), layer="below")
            fig.add_annotation(x=mx, y=1.30, text=month.strftime("%b %Y"), showarrow=False,
                               font=dict(color=T.FAINT, size=10), yanchor="bottom")
        month = _dt.date(month.year + (month.month == 12), month.month % 12 + 1, 1)

    # the spine: the chronological thread every event hangs off
    fig.add_shape(type="line", x0=0, x1=1, y0=0, y1=0,
                  line=dict(color=T.BORDER_STRONG, width=2), layer="below")

    # connectors: each node curves off the spine, and same-analyte labs chain together
    by_doc: dict[str, list[FlowNode]] = {}
    for n in nodes:
        by_doc.setdefault(n.doc_id, []).append(n)

    for n in nodes:
        dim = focus is not None and n.node_id != focus
        xs, ys = _bezier(n.x, 0.0, n.x, n.y)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
            line=dict(color=T.CATEGORY.get(n.category, T.MUTED), width=1.6),
            opacity=0.16 if dim else 0.55,
        ))

    # chain repeated measurements of the same analyte, left to right
    chains: dict[str, list[FlowNode]] = {}
    for n in nodes:
        if n.category in ("Labs", "Visits"):
            chains.setdefault(n.title, []).append(n)
    for title, chain in chains.items():
        if len(chain) < 2:
            continue
        chain = sorted(chain, key=lambda n: n.x)
        for a, b in zip(chain, chain[1:]):
            dim = focus is not None and focus not in (a.node_id, b.node_id)
            xs, ys = _bezier(a.x, a.y, b.x, b.y)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                line=dict(color=T.CATEGORY.get(a.category, T.MUTED), width=1.5),
                opacity=0.07 if dim else 0.26,
            ))

    # imaging thumbnails sit behind their node
    if show_thumbnails:
        for n in nodes:
            if n.category != "Imaging" or not n.modality:
                continue
            if focus is not None and n.node_id != focus:
                continue
            study = imaging.study_for(n.modality, n.node_id, size=(200, 200))
            fig.add_layout_image(dict(
                source=imaging.to_data_uri(study), xref="x", yref="y",
                x=n.x, y=n.y + 0.075, sizex=0.062, sizey=0.26,
                xanchor="center", yanchor="bottom", layer="above", sizing="contain",
            ))

    # Labelling every node makes the canvas unreadable past ~25 events, so beyond
    # that only anchors (documents, imaging, flagged items) stay labelled and the
    # rest are available on hover and on click.
    label_all = len(nodes) <= 26

    # nodes, one trace per category so the legend acts as a key
    for category in CATEGORIES:
        group = [n for n in nodes if n.category == category]
        if not group:
            continue
        colour = T.CATEGORY[category]
        fig.add_trace(go.Scatter(
            x=[n.x for n in group], y=[n.y for n in group],
            mode="markers+text", name=category,
            marker=dict(
                size=[20 if n.category == "Imaging" else 15 for n in group],
                color=[colour if not n.flagged else T.ROSE for n in group],
                opacity=[0.22 if (focus and n.node_id != focus) else 1.0 for n in group],
                line=dict(width=[3 if n.flagged else 2.4 for n in group], color=T.CANVAS),
                symbol=["square" if n.category == "Docs" else
                        "diamond" if n.category == "Imaging" else "circle" for n in group],
            ),
            text=[_label_for(n, label_all) for n in group],
            textposition=["top center" if n.y >= 0 else "bottom center" for n in group],
            textfont=dict(color=T.INK, size=10.5, family="Inter"),
            cliponaxis=False,
            customdata=[[n.node_id, n.title, n.subtitle,
                         n.date.strftime("%d %b %Y") if n.date else "no date",
                         n.detail[:90], n.category] for n in group],
            hovertemplate=("<b>%{customdata[1]}</b><br>%{customdata[2]}<br>"
                           "%{customdata[3]} · %{customdata[5]}<br>"
                           "<i>%{customdata[4]}</i><extra></extra>"),
        ))

    lanes_span = max(abs(n.y) for n in nodes) if nodes else 1
    fig.update_xaxes(visible=False, range=[-0.06, 1.06])
    fig.update_yaxes(visible=False, range=[-lanes_span - 0.42, lanes_span + 0.52])
    fig.update_layout(
        height=max(520, int(330 + lanes_span * 300)),
        paper_bgcolor=T.CANVAS, plot_bgcolor=T.CANVAS,
        font=dict(color=T.TEXT, size=12, family="Inter, system-ui, sans-serif"),
        margin=dict(l=20, r=20, t=42, b=30),
        hoverlabel=dict(bgcolor=T.INK, bordercolor=T.INK,
                        font=dict(color="#fff", size=12)),
        legend=dict(orientation="h", y=-0.02, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(color=T.MUTED, size=11)),
        showlegend=True,
    )
    return fig
