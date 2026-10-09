"""CAREGRAPH - medical-record intelligence engine.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import datetime as _dt
import html

import streamlit as st

from caregraph import analysis, evidence, safety, viz
from caregraph import ui_theme as T
from caregraph.extraction import ingest
from caregraph.samples import load_sample_case
from caregraph.schemas import Case, EvidenceStatus, FlagSeverity
from caregraph.timeline import build_series, document_events
from caregraph.units import display_for

st.set_page_config(page_title="CAREGRAPH", page_icon="◈", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(T.CSS, unsafe_allow_html=True)

E = html.escape


def _state() -> Case:
    if "case" not in st.session_state:
        st.session_state.case = Case()
    return st.session_state.case


def _set_case(case: Case) -> None:
    st.session_state.case = case
    st.session_state.pop("focus_node", None)


def _ingest_uploads(files, replace: bool) -> None:
    case = Case() if replace else _state()
    existing = {d.doc_id for d in case.documents}
    added = 0
    for f in files:
        doc, measurements, statements = ingest(f.name, data=f.getvalue())
        if doc.doc_id in existing:
            continue
        case.documents.append(doc)
        case.measurements.extend(measurements)
        case.statements.extend(statements)
        added += 1
    if added:
        _set_case(analysis.analyse(case))
    return added


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### ◈ CAREGRAPH")
    st.markdown('<p class="cg-muted">Evidence · changes · contradictions · next questions</p>',
                unsafe_allow_html=True)
    st.divider()

    st.markdown("**1 · Load records**")
    if st.button("Load synthetic demo set", width="stretch", type="primary"):
        with st.spinner("Ingesting and analysing four synthetic records…"):
            _set_case(load_sample_case())
        st.success("Demo set loaded.")

    uploads = st.file_uploader("Upload PDF or text records", type=["pdf", "txt", "md"],
                               accept_multiple_files=True)
    if uploads and st.button(f"Process {len(uploads)} file(s)", width="stretch"):
        with st.spinner("Extracting, cross-referencing and verifying…"):
            n = _ingest_uploads(uploads, replace=False)
        st.success(f"Added {n} document(s).") if n else st.info("Already loaded.")

    with st.expander("Paste text instead"):
        pasted = st.text_area("Record text", height=140, label_visibility="collapsed",
                              placeholder="Paste a report here if a PDF will not extract…")
        pasted_name = st.text_input("Label", value="pasted-record.txt")
        if st.button("Add pasted record", width="stretch") and pasted.strip():
            case = _state()
            doc, m, s = ingest(pasted_name or "pasted.txt", text=pasted)
            case.documents.append(doc)
            case.measurements.extend(m)
            case.statements.extend(s)
            _set_case(analysis.analyse(case))
            st.success("Added.")

    st.divider()
    st.markdown("**2 · Settings**")
    language = st.selectbox("Explanation language", list(analysis.LANGUAGES),
                            format_func=lambda k: analysis.LANGUAGES[k])
    force_offline = st.toggle("Force offline generator", value=False,
                              help="Deterministic, zero-cost. Automatically used when no API key is set.")
    if st.button("Clear session", width="stretch"):
        _set_case(Case())
        st.rerun()

    st.divider()
    st.caption("Documents are held in memory for this session only and are not written to disk.")

case = _state()

# ---------------------------------------------------------------- header
provider_note = "offline deterministic generator" if (
    force_offline or not (__import__("os").getenv("CAREGRAPH_API_KEY")
                          or __import__("os").getenv("ANTHROPIC_API_KEY"))
) else "configured API provider"
synthetic = any(d.is_synthetic for d in case.documents)

st.markdown(
    f"""<div class="cg-hero">
      <h1>CAREGRAPH</h1>
      <p class="sub">Connects multiple medical records into an evidence-linked model of
      what changed, what conflicts, and what is missing.</p>
      <div style="margin-top:12px">
        {T.tag("Evidence verified", T.GREEN)}
        {T.tag("Contradictions flagged, never resolved", T.AMBER)}
        {T.tag(provider_note, T.CYAN)}
        {T.tag("Simulated data", T.VIOLET) if synthetic else ""}
      </div>
    </div>""", unsafe_allow_html=True)

if not case.documents:
    st.markdown(
        '<div class="cg-empty"><h3>No records loaded</h3>'
        '<p>Load the synthetic demo set from the sidebar, or upload your own PDF/text records.<br>'
        'CAREGRAPH needs at least two documents to compare.</p></div>', unsafe_allow_html=True)
    st.info(safety.DISCLAIMER)
    st.stop()

integrity = evidence.graph_integrity(case)
cols = st.columns(6)
possible = sum(1 for f in case.flags if f.severity is FlagSeverity.POSSIBLE)
for col, (val, key) in zip(cols, [
    (integrity["documents"], "documents"), (integrity["facts"], "extracted facts"),
    (integrity["claims"], "generated claims"), (possible, "possible conflicts"),
    (len(case.gaps), "information gaps"), (integrity["rejected_references"], "refs rejected"),
]):
    col.markdown(T.metric(val, key), unsafe_allow_html=True)

injected = [d for d in case.documents if d.injection_findings]
if injected:
    st.warning(
        "**Model-directed text detected in uploaded documents.** "
        + ", ".join(f"`{E(d.filename)}` ({', '.join(d.injection_findings)})" for d in injected)
        + ". This text was neutralised and treated as data, not as instructions.")
errored = [d for d in case.documents if d.extraction_error]
if errored:
    st.error("Extraction problems: " + " · ".join(
        f"`{E(d.filename)}` — {E(d.extraction_error)}" for d in errored))

tabs = st.tabs(["◧ Library", "◴ Timeline", "◈ Evidence graph",
                "⚠ Contradiction radar", "◌ Missing information", "✎ Appointment brief"])

# ---------------------------------------------------------------- library
with tabs[0]:
    st.plotly_chart(viz.document_strip(case), width="stretch",
                    config={"displayModeBar": False})
    for e in document_events(case):
        doc = case.doc(e["doc_id"])
        date_label = e["date"].isoformat() if e["date"] else "no date found"
        badge = T.tag("labelled date", T.GREEN) if e["explicit"] else T.tag(
            "date unlabelled" if e["date"] else "no date", T.AMBER)
        st.markdown(
            f'<div class="cg-card"><b>{E(doc.filename)}</b> &nbsp;{badge}'
            f'<div class="cg-muted">{E(e["label"])} · {E(date_label)} · {doc.page_count} page(s) · '
            f'{e["n_measurements"]} measurements · {e["n_statements"]} statements</div></div>',
            unsafe_allow_html=True)
        with st.expander(f"Source text — {doc.filename}"):
            st.markdown(f'<div class="cg-src">{E(doc.text[:6000])}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- timeline
with tabs[1]:
    series_list = build_series(case)
    plottable = [s for s in series_list if s.points]
    if not plottable:
        st.markdown('<div class="cg-empty">No measurement could be placed on a timeline. '
                    'Values need both a date and a unit.</div>', unsafe_allow_html=True)
    else:
        # surface series that had readings held out first - that exclusion is the
        # most important thing on this tab, so it must not be hidden behind a filter
        default = [s.analyte for s in sorted(
            plottable, key=lambda s: (-len(s.excluded), -len(s.points)))[:2]]
        chosen = st.multiselect("Measurements to plot", [s.analyte for s in plottable],
                                default=default, format_func=display_for)
        st.plotly_chart(viz.timeline_figure(series_list, chosen), width="stretch")
        st.caption("Diamond markers were converted from another unit; hover shows the value as "
                   "printed in the source. Lines connect recorded values only — nothing between "
                   "two points is inferred.")

        for s in series_list:
            if s.analyte not in chosen:
                continue
            summary = s.change_summary()
            if summary:
                st.markdown(f'<div class="cg-card">{E(summary)}'
                            f'<div class="cg-muted">Describes the recorded numbers only.</div></div>',
                            unsafe_allow_html=True)
            for m, reason in s.excluded:
                st.markdown(
                    f'<div class="cg-card flagged"><b>Held out of the chart:</b> '
                    f'{E(s.label)} = {m.value:g} {E(m.unit or "(no unit)")}'
                    f'<div class="cg-muted">Reason: {E(reason)}</div>'
                    f'<div class="cg-src" style="margin-top:8px">{E(m.provenance.raw_text)}</div></div>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- evidence graph
with tabs[2]:
    left, right = st.columns([3, 2], gap="medium")
    with left:
        kinds = st.multiselect("Show node types",
                               ["document", "fact", "claim", "flag", "question"],
                               default=["document", "fact", "claim", "flag"])
        graph = evidence.build_graph(case)
        graph = {
            "nodes": [n for n in graph["nodes"] if n["kind"] in kinds],
            "edges": graph["edges"],
        }
        ids = {n["id"] for n in graph["nodes"]}
        graph["edges"] = [e for e in graph["edges"] if e["source"] in ids and e["target"] in ids]

        focus = st.session_state.get("focus_node")
        event = st.plotly_chart(viz.evidence_graph_figure(graph, focus),
                                width="stretch", on_select="rerun",
                                selection_mode="points", key="graph")
        picked = (event.get("selection", {}) or {}).get("points", []) if event else []
        if picked:
            cd = picked[0].get("customdata")
            if cd:
                st.session_state.focus_node = cd[0]
                focus = cd[0]
        if focus and st.button("Clear focus"):
            st.session_state.pop("focus_node", None)
            st.rerun()
        st.caption("Click any node to isolate it and inspect its evidence. Squares are documents, "
                   "circles extracted facts, diamonds generated claims, triangles flags, stars questions.")

    with right:
        st.markdown("#### Evidence status of generated claims")
        st.plotly_chart(viz.status_bar(integrity), width="stretch",
                        config={"displayModeBar": False})
        if integrity["rejected_references"]:
            st.error(f"{integrity['rejected_references']} source reference(s) pointed at facts that "
                     f"do not exist and were rejected by the verifier.")
        else:
            st.success("Every source reference in every claim resolves to a real extracted fact.")

        node = next((n for n in graph["nodes"] if n["id"] == focus), None) if focus else None
        if node is None:
            st.markdown('<div class="cg-empty">Select a node to inspect it.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown("#### Inspector")
            st.markdown(f'<div class="cg-card"><div class="cg-muted">{E(node["kind"])}</div>'
                        f'<b>{E(node["label"])}</b></div>', unsafe_allow_html=True)
            if node["kind"] == "claim":
                claim = next(c for c in case.claims if c.claim_id == node["id"])
                colour = T.STATUS_COLOR[claim.status.value]
                st.markdown(T.tag(T.STATUS_LABEL[claim.status.value], colour), unsafe_allow_html=True)
                st.write(claim.text)
                if claim.caveat:
                    st.markdown(f'<div class="cg-muted">⚠ {E(claim.caveat)}</div>',
                                unsafe_allow_html=True)
                st.markdown("**Supporting source text**")
                for fid in claim.evidence_ids:
                    fact = case.fact(fid)
                    if fact:
                        doc = case.doc(fact.provenance.doc_id)
                        st.markdown(
                            f'<div class="cg-muted">{E(doc.filename if doc else "?")} · '
                            f'page {fact.provenance.page}, line {fact.provenance.line}</div>'
                            f'<div class="cg-src">{E(fact.provenance.raw_text)}</div>',
                            unsafe_allow_html=True)
                if not claim.evidence_ids:
                    st.warning("This claim cites no resolvable evidence.")
            elif node["kind"] == "fact":
                fact = case.fact(node["id"])
                doc = case.doc(fact.provenance.doc_id)
                st.markdown(f'<div class="cg-muted">{E(doc.filename if doc else "?")} · '
                            f'page {fact.provenance.page}, line {fact.provenance.line}</div>'
                            f'<div class="cg-src">{E(fact.provenance.raw_text)}</div>',
                            unsafe_allow_html=True)
                if st.button("Explain this in plain language", key=f"ex_{node['id']}"):
                    with st.spinner("Generating and verifying…"):
                        claim, result = analysis.explain_facts(
                            case, [node["id"]], language=language, force_offline=force_offline)
                    st.markdown(T.tag(T.STATUS_LABEL[claim.status.value],
                                      T.STATUS_COLOR[claim.status.value]), unsafe_allow_html=True)
                    st.write(claim.text)
                    if claim.caveat:
                        st.caption(claim.caveat)
                    if result.error:
                        st.warning(result.error)
                    st.caption(f"Generated by: {claim.generator}"
                               + (" (simulated output)" if result.simulated else ""))
            elif node["kind"] == "flag":
                flag = next(f for f in case.flags if f.flag_id == node["id"])
                st.write(flag.reason)
                st.info(f"Needs clarification: {flag.needs_clarification}")
            elif node["kind"] == "document":
                doc = case.doc(node["id"])
                st.markdown(f'<div class="cg-src">{E(doc.text[:2500])}</div>',
                            unsafe_allow_html=True)

# ---------------------------------------------------------------- contradictions
with tabs[3]:
    if not case.flags:
        st.markdown('<div class="cg-empty">No inconsistency could be justified from these '
                    'documents.</div>', unsafe_allow_html=True)
    for flag in case.flags:
        possible_conflict = flag.severity is FlagSeverity.POSSIBLE
        css = "conflict" if possible_conflict else "flagged"
        badge = T.tag("possible factual contradiction", T.ROSE) if possible_conflict else \
            T.tag("confirmed formatting inconsistency", T.AMBER)
        st.markdown(
            f'<div class="cg-card {css}">{badge}<br><b style="font-size:1.05rem">{E(flag.title)}</b>'
            f'<p style="margin:8px 0 4px 0">{E(flag.reason)}</p>'
            f'<div class="cg-muted"><b>Needs human clarification:</b> '
            f'{E(flag.needs_clarification)}</div></div>', unsafe_allow_html=True)
        if flag.evidence_ids:
            srcs = st.columns(min(len(flag.evidence_ids), 2))
            for col, fid in zip(srcs, flag.evidence_ids[:2]):
                fact = case.fact(fid)
                if not fact:
                    continue
                doc = case.doc(fact.provenance.doc_id)
                with col:
                    st.markdown(
                        f'<div class="cg-muted">{E(doc.filename if doc else "?")} · '
                        f'page {fact.provenance.page}, line {fact.provenance.line}</div>'
                        f'<div class="cg-src">{E(fact.provenance.raw_text)}</div>',
                        unsafe_allow_html=True)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- gaps
with tabs[4]:
    st.markdown('<p class="cg-muted">What the records document, what they leave uncertain, and '
                'what is simply absent. CAREGRAPH reports absence; it never fills it in.</p>',
                unsafe_allow_html=True)
    if not case.gaps:
        st.markdown('<div class="cg-empty">No information gaps detected.</div>',
                    unsafe_allow_html=True)
    for gap in case.gaps:
        docs = ", ".join(E(case.doc(d).filename) for d in gap.related_doc_ids if case.doc(d))
        st.markdown(
            f'<div class="cg-card flagged"><b>{E(gap.label)}</b>'
            f'<p style="margin:6px 0 0 0">{E(gap.detail)}</p>'
            + (f'<div class="cg-muted" style="margin-top:6px">Affects: {docs}</div>' if docs else "")
            + '</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- brief
with tabs[5]:
    st.markdown("#### Prioritised questions for your appointment")
    for q in case.questions[:15]:
        colour = {1: T.ROSE, 2: T.AMBER, 3: T.CYAN}[min(q.priority, 3)]
        label = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}[min(q.priority, 3)]
        st.markdown(
            f'<div class="cg-card">{T.tag(label, colour)}<b>{E(q.text)}</b>'
            f'<div class="cg-muted">{E(q.rationale)}</div></div>', unsafe_allow_html=True)

    st.divider()
    brief = analysis.appointment_brief(case)
    st.download_button("Download brief (Markdown)", brief,
                       file_name=f"caregraph-brief-{_dt.date.today()}.md",
                       mime="text/markdown", width="stretch")
    with st.expander("Preview brief", expanded=True):
        st.markdown(brief)

st.divider()
st.caption(safety.DISCLAIMER)
