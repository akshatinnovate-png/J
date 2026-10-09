"""Plotly figures. Every figure is built from real extracted data."""
from __future__ import annotations

import math

import plotly.graph_objects as go

from . import ui_theme as T
from .schemas import Case
from .timeline import Series, document_events


def _layout(fig: go.Figure, height: int, **kw) -> go.Figure:
    base = dict(
        height=height, paper_bgcolor=T.BG, plot_bgcolor=T.SURFACE,
        font=dict(color=T.TEXT, size=13, family="Inter, system-ui, sans-serif"),
        margin=dict(l=52, r=22, t=34, b=42),
        hoverlabel=dict(bgcolor=T.SURFACE_2, bordercolor=T.CYAN,
                        font=dict(color=T.TEXT, size=12)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=T.MUTED)),
    )
    base.update(kw)
    fig.update_layout(**base)
    fig.update_xaxes(gridcolor=T.BORDER, zerolinecolor=T.BORDER, linecolor=T.BORDER)
    fig.update_yaxes(gridcolor=T.BORDER, zerolinecolor=T.BORDER, linecolor=T.BORDER)
    return fig


def timeline_figure(series_list: list[Series], selected: list[str]) -> go.Figure:
    """Measurement series over time, one facet per analyte.

    Faceting rather than a shared axis is deliberate: analytes have different
    magnitudes, and plotting HbA1c (~7) against glucose (~140) on one scale makes
    the smaller series look flat. Each facet also carries its own reference band.
    """
    from plotly.subplots import make_subplots

    shown = [s for s in series_list if s.analyte in selected and s.points]
    if not shown:
        fig = go.Figure()
        fig.add_annotation(text="No comparable measurements selected",
                           showarrow=False, font=dict(color=T.MUTED, size=14))
        return _layout(fig, 420)

    rows = len(shown)
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.09 / max(rows - 1, 1) if rows > 1 else 0.1,
        subplot_titles=[f"{s.label} ({s.unit or 'no unit'})" for s in shown],
    )

    for idx, s in enumerate(shown, start=1):
        colour = T.SERIES_COLORS[(idx - 1) % len(T.SERIES_COLORS)]
        lows = [p.ref_low for p in s.points if p.ref_low is not None]
        highs = [p.ref_high for p in s.points if p.ref_high is not None]
        if lows and highs:
            fig.add_hrect(y0=min(lows), y1=max(highs), fillcolor=T.GREEN, opacity=0.08,
                          line_width=0, row=idx, col=1)

        fig.add_trace(go.Scatter(
            x=[p.date for p in s.points],
            y=[p.value for p in s.points],
            mode="lines+markers",
            name=f"{s.label} ({s.unit or 'no unit'})",
            showlegend=False,
            line=dict(color=colour, width=2.4),
            marker=dict(size=11, color=colour, line=dict(width=1.5, color=T.BG),
                        symbol=["diamond" if p.converted else "circle" for p in s.points]),
            customdata=[[p.fact_id, p.raw_text[:90],
                         f"{p.original_value:g} {p.original_unit or ''}",
                         "converted" if p.converted else "as printed",
                         p.context or "not stated"] for p in s.points],
            hovertemplate=(
                f"<b>{s.label}</b><br>%{{x|%d %b %Y}}<br>"
                f"Plotted: %{{y:g}} {s.unit or ''}<br>"
                "Printed in source: %{customdata[2]} (%{customdata[3]})<br>"
                "Sampling context: %{customdata[4]}<br>"
                "<i>%{customdata[1]}</i><extra></extra>"
            ),
        ), row=idx, col=1)

        if lows and highs:
            fig.add_annotation(
                text="reference range printed in source", xref=f"x{idx if idx > 1 else ''} domain",
                yref=f"y{idx if idx > 1 else ''}", x=0.01, y=max(highs), showarrow=False,
                font=dict(color=T.MUTED, size=10), xanchor="left", yanchor="bottom",
            )

    fig.update_annotations(font=dict(color=T.TEXT, size=13))
    fig.update_xaxes(title_text="date recorded in source", row=rows, col=1)
    return _layout(fig, max(230 * rows, 330), hovermode="closest", showlegend=False)


def document_strip(case: Case) -> go.Figure:
    """Documents as events on a date axis. Undated ones are shown apart, not guessed."""
    events = document_events(case)
    dated = [e for e in events if e["dated"]]
    undated = [e for e in events if not e["dated"]]
    fig = go.Figure()
    if dated:
        fig.add_trace(go.Scatter(
            x=[e["date"] for e in dated], y=[1] * len(dated), mode="markers+text",
            marker=dict(size=19, color=T.CYAN, symbol="square",
                        line=dict(width=1.5, color=T.BG)),
            text=[e["label"] for e in dated],
            # stagger labels so documents sharing a date stay readable
            textposition=["top center" if i % 2 == 0 else "bottom center"
                          for i in range(len(dated))],
            textfont=dict(color=T.MUTED, size=11),
            customdata=[[e["filename"], e["n_measurements"], e["n_statements"],
                         "labelled" if e["explicit"] else "unlabelled"] for e in dated],
            hovertemplate=("<b>%{customdata[0]}</b><br>%{x|%d %b %Y} (%{customdata[3]} date)<br>"
                           "%{customdata[1]} measurements · %{customdata[2]} statements<extra></extra>"),
            name="dated documents",
        ))
    if undated:
        fig.add_trace(go.Scatter(
            x=[None] * len(undated), y=[1] * len(undated), mode="markers",
            marker=dict(size=19, color=T.AMBER, symbol="square-open"),
            name=f"{len(undated)} undated document(s) - not positioned",
        ))
    fig.update_yaxes(visible=False, range=[0.3, 1.8])
    return _layout(fig, 180, showlegend=bool(undated), xaxis_title=None)


def _layout_graph(nodes: list[dict], edges: list[dict]) -> dict[str, tuple[float, float]]:
    """Layered left-to-right layout: documents -> facts -> claims/flags/questions.

    A force layout turns ~80 nodes into spaghetti. Layering makes the direction of
    evidence readable at a glance, and ordering each layer by the average position
    of its neighbours (barycentre) keeps the connecting lines from crossing.
    """
    layers = {"document": 0.0, "fact": 1.0, "claim": 2.0, "flag": 2.0, "question": 3.0}
    by_layer: dict[float, list[dict]] = {}
    for n in nodes:
        by_layer.setdefault(layers.get(n["kind"], 2.0), []).append(n)

    # claims and flags share a column; keep them in separate bands within it
    for col, items in by_layer.items():
        items.sort(key=lambda n: (n["kind"], n.get("doc_id") or "", n["label"]))

    pos: dict[str, tuple[float, float]] = {}

    def assign(col: float, items: list[dict]) -> None:
        span = max(len(items) - 1, 1)
        for i, n in enumerate(items):
            pos[n["id"]] = (col, 1.0 - 2.0 * i / span)

    ordered_cols = sorted(by_layer)
    for col in ordered_cols:
        assign(col, by_layer[col])

    # two barycentre sweeps: reorder each layer by the mean y of its neighbours
    adjacency: dict[str, list[str]] = {}
    for e in edges:
        adjacency.setdefault(e["source"], []).append(e["target"])
        adjacency.setdefault(e["target"], []).append(e["source"])

    for _ in range(2):
        for col in ordered_cols:
            items = by_layer[col]
            def barycentre(n: dict) -> float:
                ys = [pos[m][1] for m in adjacency.get(n["id"], []) if m in pos]
                return sum(ys) / len(ys) if ys else pos[n["id"]][1]
            items.sort(key=lambda n: (n["kind"] if col == 2.0 else "", -barycentre(n)))
            assign(col, items)

    return pos


def evidence_graph_figure(graph: dict, focus: str | None = None) -> go.Figure:
    """The signature view: documents -> facts -> claims, flags and questions."""
    nodes, edges = graph["nodes"], graph["edges"]
    fig = go.Figure()
    if not nodes:
        fig.add_annotation(text="Upload documents to build the evidence graph",
                           showarrow=False, font=dict(color=T.MUTED, size=14))
        return _layout(fig, 560)

    pos = _layout_graph(nodes, edges)
    neighbours: set[str] = set()
    if focus:
        neighbours = {focus} | {e["target"] for e in edges if e["source"] == focus} \
                             | {e["source"] for e in edges if e["target"] == focus}

    for relation, dash in (("contains", "dot"), ("supported_by", "solid"),
                           ("flags", "dash"), ("asks_about", "dashdot")):
        xs: list[float | None] = []
        ys: list[float | None] = []
        for e in edges:
            if e["relation"] != relation:
                continue
            if e["source"] not in pos or e["target"] not in pos:
                continue
            if focus and not (e["source"] in neighbours and e["target"] in neighbours):
                continue
            x0, y0 = pos[e["source"]]
            x1, y1 = pos[e["target"]]
            xs += [x0, x1, None]
            ys += [y0, y1, None]
        if xs:
            colour = {"contains": T.BORDER, "supported_by": T.GREEN,
                      "flags": T.ROSE, "asks_about": T.VIOLET}[relation]
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=True,
                name=relation.replace("_", " "),
                line=dict(color=colour, width=1.5 if relation == "contains" else 2.1, dash=dash),
                opacity=0.75,
            ))

    for kind in ("document", "fact", "claim", "flag", "question"):
        group = [n for n in nodes if n["kind"] == kind and n["id"] in pos]
        if not group:
            continue
        colours = []
        for n in group:
            if kind == "claim":
                colours.append(T.STATUS_COLOR.get(n.get("status", ""), T.MUTED))
            elif kind == "flag":
                colours.append(T.ROSE if n.get("severity", "").startswith("possible") else T.AMBER)
            else:
                colours.append(T.NODE_COLOR[kind])
        sizes = [{"document": 30, "fact": 15, "claim": 22, "flag": 24, "question": 18}[kind]] * len(group)
        opac = [1.0 if (not focus or n["id"] in neighbours) else 0.16 for n in group]
        fig.add_trace(go.Scatter(
            x=[pos[n["id"]][0] for n in group],
            y=[pos[n["id"]][1] for n in group],
            mode="markers", name=kind,
            marker=dict(size=sizes, color=colours, opacity=opac,
                        line=dict(width=2, color=T.BG),
                        symbol={"document": "square", "fact": "circle", "claim": "diamond",
                                "flag": "triangle-up", "question": "star"}[kind]),
            customdata=[[n["id"], n["label"], (n.get("detail") or "")[:160],
                         T.STATUS_LABEL.get(n.get("status", ""), kind)] for n in group],
            hovertemplate=("<b>%{customdata[1]}</b><br>%{customdata[3]}<br>"
                           "<i>%{customdata[2]}</i><extra></extra>"),
        ))
    for col, title in ((0.0, "DOCUMENTS"), (1.0, "EXTRACTED FACTS"),
                       (2.0, "CLAIMS & FLAGS"), (3.0, "QUESTIONS")):
        if any(abs(p[0] - col) < 1e-9 for p in pos.values()):
            fig.add_annotation(x=col, y=1.22, text=title, showarrow=False,
                               font=dict(color=T.MUTED, size=10.5), xanchor="center")

    used = sorted({round(p[0], 6) for p in pos.values()})
    fig.update_xaxes(visible=False,
                     range=[min(used) - 0.45, max(used) + 0.45])
    fig.update_yaxes(visible=False, range=[-1.18, 1.38])
    return _layout(fig, 580, showlegend=True, plot_bgcolor=T.BG,
                   legend=dict(orientation="h", y=-0.04, font=dict(color=T.MUTED)))


def status_bar(integrity: dict) -> go.Figure:
    """Evidence status distribution - real counts from the verifier."""
    by = integrity.get("claims_by_status", {})
    order = ["supported", "partially_supported", "conflicting_evidence",
             "unverified", "insufficient_information"]
    items = [(s, by.get(s, 0)) for s in order if by.get(s, 0)]
    fig = go.Figure()
    if not items:
        fig.add_annotation(text="No claims generated yet", showarrow=False,
                           font=dict(color=T.MUTED))
        return _layout(fig, 160)
    fig.add_trace(go.Bar(
        y=[T.STATUS_LABEL[s] for s, _ in items],
        x=[c for _, c in items], orientation="h",
        marker=dict(color=[T.STATUS_COLOR[s] for s, _ in items]),
        text=[c for _, c in items], textposition="outside",
        textfont=dict(color=T.TEXT),
        hovertemplate="%{y}: %{x} claim(s)<extra></extra>",
    ))
    headroom = max(c for _, c in items) * 1.18 + 0.5
    fig.update_xaxes(range=[0, headroom])
    return _layout(fig, 40 + 46 * len(items), showlegend=False, xaxis_title=None,
                   margin=dict(l=150, r=30, t=18, b=30))
