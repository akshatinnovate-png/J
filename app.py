"""CAREGRAPH - medical-record intelligence engine.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import datetime as _dt
import html
import os

import streamlit as st

from caregraph import analysis, entry, evidence, flowcanvas, imaging, safety, viz
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
    st.session_state.pop("flow_focus", None)


def _ingest_uploads(files) -> int:
    case = _state()
    existing = {d.doc_id for d in case.documents}
    added = 0
    for f in files:
        doc, measurements, statements, images = ingest(f.name, data=f.getvalue())
        if doc.doc_id in existing:
            continue
        case.documents.append(doc)
        case.measurements.extend(measurements)
        case.statements.extend(statements)
        case.imaging.extend(images)
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
        with st.spinner("Ingesting and analysing…"):
            _set_case(load_sample_case())
        st.success("Demo set loaded.")

    uploads = st.file_uploader("Upload PDF or text records", type=["pdf", "txt", "md"],
                               accept_multiple_files=True)
    if uploads and st.button(f"Process {len(uploads)} file(s)", width="stretch"):
        with st.spinner("Extracting, cross-referencing and verifying…"):
            n = _ingest_uploads(uploads)
        st.success(f"Added {n} document(s).") if n else st.info("Already loaded.")

    with st.expander("Paste text instead"):
        pasted = st.text_area("Record text", height=130, label_visibility="collapsed",
                              placeholder="Paste a report here if a PDF will not extract…")
        pasted_name = st.text_input("Label", value="pasted-record.txt")
        if st.button("Add pasted record", width="stretch") and pasted.strip():
            _set_case(entry.add_document(_state(), pasted_name or "pasted.txt",
                                         pasted, is_synthetic=False))
            st.success("Added.")

    st.divider()
    st.markdown("**2 · Settings**")
    language = st.selectbox("Explanation language", list(analysis.LANGUAGES),
                            format_func=lambda k: analysis.LANGUAGES[k])
    force_offline = st.toggle("Force offline generator", value=False,
                              help="Deterministic and free. Used automatically with no API key.")
    if st.button("Clear session", width="stretch"):
        _set_case(Case())
        st.rerun()

    st.divider()
    st.caption("Records are held in memory for this session only and are never written to disk.")

case = _state()
has_key = bool(os.getenv("CAREGRAPH_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
provider_note = ("offline deterministic generator"
                 if (force_offline or not has_key) else "configured API provider")
synthetic = any(d.is_synthetic for d in case.documents)

st.markdown(
    f"""<div class="cg-hero">
      <h1>CAREGRAPH</h1>
      <p class="sub">Connects multiple medical records into an evidence-linked model of
      what changed, what conflicts, and what is missing.</p>
      <div style="margin-top:11px">
        {T.tag("Evidence verified", T.GREEN, T.GREEN_SOFT)}
        {T.tag("Contradictions flagged, never resolved", T.AMBER, T.AMBER_SOFT)}
        {T.tag(provider_note, T.BLUE, T.BLUE_SOFT)}
        {T.tag("Simulated data", T.VIOLET, "#EDE9FE") if synthetic else ""}
      </div>
    </div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- empty state
if not case.documents:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown(
            '<div class="cg-empty"><h3>No records loaded</h3>'
            '<p>Load the synthetic demo set, upload your own PDF or text records, '
            'or type records in by hand below.<br>'
            'CAREGRAPH needs at least two documents to compare.</p></div>',
            unsafe_allow_html=True)
    with right:
        st.markdown("#### What it will build")
        for title, body in [
            ("Care flow", "Every record event on one chronological canvas."),
            ("Evidence graph", "Each claim traced to the exact line it came from."),
            ("Contradiction radar", "Cross-document conflicts, shown side by side."),
            ("Imaging", "A simulated illustration for every study named in your records."),
        ]:
            st.markdown(f'<div class="cg-card"><b>{title}</b>'
                        f'<div class="cg-muted">{body}</div></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### Enter a record by hand")
    st.caption("Typed entries run through the same extractor as an uploaded PDF, "
               "with provenance pointing back at the line you typed.")

    with st.form("first_entry"):
        c1, c2 = st.columns(2)
        title = c1.text_input("Document type", value="Laboratory Report")
        doc_date = c2.date_input("Collection date", value=_dt.date.today())
        body = st.text_area(
            "Record lines (one per line)", height=180,
            value=("HbA1c 7.2 % (ref 4.0-5.6)\n"
                   "Fasting glucose 142 mg/dL (ref 70-99)\n"
                   "Blood pressure 138/86 mmHg\n"
                   "Metformin 500 mg twice daily\n"
                   "Chest X-ray: lung fields clear\n"
                   "Advised to repeat the lipid panel in three months"))
        if st.form_submit_button("Add record", type="primary"):
            text = entry.compose_document(title, doc_date, body.splitlines())
            _set_case(entry.add_document(_state(), f"typed-{doc_date}.txt", text,
                                         is_synthetic=True))
            st.rerun()

    st.info(safety.DISCLAIMER)
    st.stop()

# ---------------------------------------------------------------- metrics
integrity = evidence.graph_integrity(case)
possible = sum(1 for f in case.flags if f.severity is FlagSeverity.POSSIBLE)
cols = st.columns(7)
for col, (val, key) in zip(cols, [
    (integrity["documents"], "documents"), (integrity["facts"], "extracted facts"),
    (len(case.imaging), "imaging studies"), (integrity["claims"], "claims"),
    (possible, "possible conflicts"), (len(case.gaps), "gaps"),
    (integrity["rejected_references"], "refs rejected"),
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

tabs = st.tabs(["◉ Care flow", "◧ Library", "◴ Timeline", "◈ Evidence graph",
                "⚠ Contradictions", "⬚ Imaging", "◌ Gaps", "✎ Brief", "⊕ Add record"])

# ---------------------------------------------------------------- care flow
with tabs[0]:
    rail, canvas = st.columns([1, 3.6], gap="medium")

    with rail:
        series = [s for s in build_series(case) if len(s.points) >= 2]
        headline = max(series, key=lambda s: len(s.points), default=None)
        if headline:
            first, last = headline.points[0], headline.points[-1]
            direction = ("rising" if last.value > first.value
                         else "falling" if last.value < first.value else "flat")
            st.markdown(
                f'<div class="cg-condition"><div class="lbl">Most-tracked measure</div>'
                f'<div class="nm">{E(headline.label)}</div>'
                f'<div class="mk">{len(headline.points)} readings · {direction} · '
                f'{first.value:g} → {last.value:g} {E(headline.unit or "")}</div></div>',
                unsafe_allow_html=True)

        team = analysis.care_team(case)
        st.markdown("###### Clinicians named in these records")
        if team:
            rows = "".join(T.person_row(p["initials"], p["name"], p["role"], p["documents"])
                           for p in team)
            st.markdown(f'<div class="cg-rail">{rows}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="cg-muted">No clinician is named in these documents. '
                        'CAREGRAPH does not invent one.</div>', unsafe_allow_html=True)

        facs = analysis.facilities(case)
        if facs:
            st.markdown("###### Issuing sources")
            rows = "".join(
                T.person_row("".join(w[0] for w in f["name"].split()[:2]).upper(),
                             f["name"], "Issuing source", f["documents"]) for f in facs)
            st.markdown(f'<div class="cg-rail">{rows}</div>', unsafe_allow_html=True)

    with canvas:
        chosen = st.multiselect("Show", flowcanvas.CATEGORIES,
                                default=flowcanvas.CATEGORIES, label_visibility="collapsed")
        thumbs = st.toggle("Show imaging thumbnails on the canvas", value=True)
        nodes = flowcanvas.layout(flowcanvas.build_nodes(case, chosen))
        flow_focus = st.session_state.get("flow_focus")
        event = st.plotly_chart(
            flowcanvas.figure(case, nodes, focus=flow_focus, show_thumbnails=thumbs),
            width="stretch", on_select="rerun", selection_mode="points", key="flow")
        picked = (event.get("selection", {}) or {}).get("points", []) if event else []
        if picked and picked[0].get("customdata"):
            st.session_state.flow_focus = picked[0]["customdata"][0]
            flow_focus = st.session_state.flow_focus
        undated = [n for n in flowcanvas.build_nodes(case, chosen) if n.date is None]
        st.caption("Click any node to isolate it. Events without a readable date are not "
                   "placed on the canvas and appear under Gaps.")

        node = next((n for n in nodes if n.node_id == flow_focus), None)
        if node:
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(
                    f'<div class="cg-card"><div class="cg-muted">{E(node.category)} · '
                    f'{E(node.date.strftime("%d %B %Y"))}</div>'
                    f'<b style="font-size:1.05rem">{E(node.title)}</b> — {E(node.subtitle)}'
                    f'<div class="cg-src" style="margin-top:9px">{E(node.detail)}</div></div>',
                    unsafe_allow_html=True)
                doc = case.doc(node.doc_id)
                if doc:
                    st.caption(f"Source: {doc.filename}")
                if st.button("Clear selection"):
                    st.session_state.pop("flow_focus", None)
                    st.rerun()
            with c2:
                if node.modality:
                    study = imaging.study_for(node.modality, node.node_id, size=(300, 300))
                    st.image(imaging.to_png_bytes(study), width="stretch")
                    st.markdown(T.tag("Simulated illustration", T.ROSE, T.ROSE_SOFT),
                                unsafe_allow_html=True)

# ---------------------------------------------------------------- library
with tabs[1]:
    st.plotly_chart(viz.document_strip(case), width="stretch",
                    config={"displayModeBar": False})
    for e in document_events(case):
        doc = case.doc(e["doc_id"])
        date_label = e["date"].isoformat() if e["date"] else "no date found"
        badge = (T.tag("labelled date", T.GREEN, T.GREEN_SOFT) if e["explicit"]
                 else T.tag("date unlabelled" if e["date"] else "no date", T.AMBER, T.AMBER_SOFT))
        n_img = sum(1 for r in case.imaging if r.provenance.doc_id == doc.doc_id)
        st.markdown(
            f'<div class="cg-card"><b>{E(doc.filename)}</b> &nbsp;{badge}'
            f'<div class="cg-muted">{E(e["label"])} · {E(date_label)} · {doc.page_count} page(s) · '
            f'{e["n_measurements"]} measurements · {e["n_statements"]} statements · '
            f'{n_img} imaging</div></div>', unsafe_allow_html=True)
        with st.expander(f"Source text — {doc.filename}"):
            st.markdown(f'<div class="cg-src">{E(doc.text[:6000])}</div>',
                        unsafe_allow_html=True)

# ---------------------------------------------------------------- timeline
with tabs[2]:
    series_list = build_series(case)
    plottable = [s for s in series_list if s.points]
    if not plottable:
        st.markdown('<div class="cg-empty">No measurement could be placed on a timeline. '
                    'Values need both a date and a unit.</div>', unsafe_allow_html=True)
    else:
        default = [s.analyte for s in sorted(
            plottable, key=lambda s: (-len(s.excluded), -len(s.points)))[:2]]
        chosen = st.multiselect("Measurements to plot", [s.analyte for s in plottable],
                                default=default, format_func=display_for)
        st.plotly_chart(viz.timeline_figure(series_list, chosen), width="stretch")
        st.caption("Diamond markers were converted from another unit; hover shows the value as "
                   "printed in the source. Lines connect recorded values only.")
        for s in series_list:
            if s.analyte not in chosen:
                continue
            summary = s.change_summary()
            if summary:
                st.markdown(f'<div class="cg-card">{E(summary)}'
                            f'<div class="cg-muted">Describes the recorded numbers only.</div>'
                            f'</div>', unsafe_allow_html=True)
            for m, reason in s.excluded:
                st.markdown(
                    f'<div class="cg-card flagged"><b>Held out of the chart:</b> '
                    f'{E(s.label)} = {m.value:g} {E(m.unit or "(no unit)")}'
                    f'<div class="cg-muted">Reason: {E(reason)}</div>'
                    f'<div class="cg-src" style="margin-top:8px">{E(m.provenance.raw_text)}</div>'
                    f'</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- evidence graph
with tabs[3]:
    left, right = st.columns([3, 2], gap="medium")
    with left:
        kinds = st.multiselect("Show node types",
                               ["document", "fact", "claim", "flag", "question"],
                               default=["document", "fact", "claim", "flag"])
        graph = evidence.build_graph(case)
        graph = {"nodes": [n for n in graph["nodes"] if n["kind"] in kinds],
                 "edges": graph["edges"]}
        ids = {n["id"] for n in graph["nodes"]}
        graph["edges"] = [e for e in graph["edges"]
                          if e["source"] in ids and e["target"] in ids]

        focus = st.session_state.get("focus_node")
        event = st.plotly_chart(viz.evidence_graph_figure(graph, focus), width="stretch",
                                on_select="rerun", selection_mode="points", key="graph")
        picked = (event.get("selection", {}) or {}).get("points", []) if event else []
        if picked and picked[0].get("customdata"):
            st.session_state.focus_node = picked[0]["customdata"][0]
            focus = st.session_state.focus_node
        if focus and st.button("Clear focus"):
            st.session_state.pop("focus_node", None)
            st.rerun()
        st.caption("Click any node to isolate it and inspect its evidence.")

    with right:
        st.markdown("#### Evidence status of generated claims")
        st.plotly_chart(viz.status_bar(integrity), width="stretch",
                        config={"displayModeBar": False})
        if integrity["rejected_references"]:
            st.error(f"{integrity['rejected_references']} source reference(s) pointed at facts "
                     f"that do not exist and were rejected by the verifier.")
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
                st.markdown(T.tag(T.STATUS_LABEL[claim.status.value],
                                  T.STATUS_COLOR[claim.status.value],
                                  T.STATUS_SOFT[claim.status.value]), unsafe_allow_html=True)
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
                if node.get("modality"):
                    st.image(imaging.to_png_bytes(
                        imaging.study_for(node["modality"], node["id"], size=(280, 280))),
                        width="stretch")
                    st.markdown(T.tag("Simulated illustration", T.ROSE, T.ROSE_SOFT),
                                unsafe_allow_html=True)
                if st.button("Explain this in plain language", key=f"ex_{node['id']}"):
                    with st.spinner("Generating and verifying…"):
                        claim, result = analysis.explain_facts(
                            case, [node["id"]], language=language, force_offline=force_offline)
                    st.markdown(T.tag(T.STATUS_LABEL[claim.status.value],
                                      T.STATUS_COLOR[claim.status.value],
                                      T.STATUS_SOFT[claim.status.value]), unsafe_allow_html=True)
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
with tabs[4]:
    if not case.flags:
        st.markdown('<div class="cg-empty">No inconsistency could be justified from these '
                    'documents.</div>', unsafe_allow_html=True)
    for flag in case.flags:
        is_conflict = flag.severity is FlagSeverity.POSSIBLE
        badge = (T.tag("possible factual contradiction", T.ROSE, T.ROSE_SOFT) if is_conflict
                 else T.tag("confirmed formatting inconsistency", T.AMBER, T.AMBER_SOFT))
        st.markdown(
            f'<div class="cg-card {"conflict" if is_conflict else "flagged"}">{badge}<br>'
            f'<b style="font-size:1.05rem">{E(flag.title)}</b>'
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
        st.markdown("<div style='height:9px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- imaging
with tabs[5]:
    st.warning("**Every image on this tab is generated, not acquired.** CAREGRAPH receives no "
               "pixel data. When a document names a study, it renders an illustration of that "
               "modality so the record has something to show. These are drawn procedurally and "
               "carry a watermark burned into the pixels. They must not be read clinically.")
    if not case.imaging:
        st.markdown('<div class="cg-empty">No imaging study is named in these records.<br>'
                    'Mention one (for example "MRI Brain" or "Chest X-ray") and it will '
                    'appear here.</div>', unsafe_allow_html=True)
    else:
        for row_start in range(0, len(case.imaging), 3):
            row = case.imaging[row_start:row_start + 3]
            cols = st.columns(3)
            for col, rec in zip(cols, row):
                with col:
                    study = imaging.study_for(rec.modality, rec.fact_id, size=(360, 360))
                    st.image(imaging.to_png_bytes(study), width="stretch")
                    doc = case.doc(rec.provenance.doc_id)
                    st.markdown(
                        f'<div class="cg-card"><b>{E(study.modality_label)}</b>'
                        f'<div class="cg-muted">{E(rec.observed_on.isoformat() if rec.observed_on else "no date")}'
                        f' · {E(doc.filename if doc else "?")} line {rec.provenance.line}</div>'
                        f'<div class="cg-src" style="margin-top:8px">{E(rec.report_text or "")}</div>'
                        f'<div style="margin-top:8px">'
                        f'<span class="cg-simbadge">SIMULATED ILLUSTRATION</span></div></div>',
                        unsafe_allow_html=True)

# ---------------------------------------------------------------- gaps
with tabs[6]:
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
with tabs[7]:
    st.markdown("#### Prioritised questions for your appointment")
    for q in case.questions[:15]:
        colour = {1: T.ROSE, 2: T.AMBER, 3: T.BLUE}[min(q.priority, 3)]
        soft = {1: T.ROSE_SOFT, 2: T.AMBER_SOFT, 3: T.BLUE_SOFT}[min(q.priority, 3)]
        label = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}[min(q.priority, 3)]
        st.markdown(
            f'<div class="cg-card">{T.tag(label, colour, soft)}<b>{E(q.text)}</b>'
            f'<div class="cg-muted">{E(q.rationale)}</div></div>', unsafe_allow_html=True)

    st.divider()
    brief = analysis.appointment_brief(case)
    st.download_button("Download brief (Markdown)", brief,
                       file_name=f"caregraph-brief-{_dt.date.today()}.md",
                       mime="text/markdown", width="stretch")
    with st.expander("Preview brief", expanded=True):
        st.markdown(brief)

# ---------------------------------------------------------------- add record
with tabs[8]:
    st.markdown("#### Add a record by hand")
    st.caption("Everything typed here is composed into a document and run through the same "
               "extractor as an upload, so it is verified on identical terms.")

    c1, c2 = st.columns(2)
    doc_title = c1.text_input("Document type", value="Laboratory Report", key="e_title")
    doc_date = c2.date_input("Collection date", value=_dt.date.today(), key="e_date")

    lines: list[str] = []
    with st.expander("Lab measurement", expanded=True):
        a1, a2, a3, a4, a5 = st.columns([2, 1, 1, 1, 1])
        analyte = a1.selectbox("Analyte", entry.ENTRY_ANALYTES, format_func=display_for)
        value = a2.number_input("Value", value=7.2, step=0.1, format="%.2f")
        unit = a3.selectbox("Unit", entry.ENTRY_UNITS.get(analyte, ["—"]))
        ref_lo = a4.number_input("Ref low", value=0.0, step=0.1, format="%.2f")
        ref_hi = a5.number_input("Ref high", value=0.0, step=0.1, format="%.2f")
        if st.checkbox("Include this measurement", value=True, key="inc_meas"):
            lines.append(entry.measurement_line(
                analyte, value, unit,
                ref_lo if ref_hi > ref_lo else None,
                ref_hi if ref_hi > ref_lo else None))

    with st.expander("Vitals"):
        v1, v2 = st.columns(2)
        sys_bp = v1.number_input("Systolic", value=138, step=1)
        dia_bp = v2.number_input("Diastolic", value=86, step=1)
        if st.checkbox("Include blood pressure", key="inc_bp"):
            lines.append(entry.bp_line(sys_bp, dia_bp))

    with st.expander("Medication"):
        m1, m2, m3 = st.columns(3)
        med = m1.text_input("Name", value="Metformin")
        dose = m2.text_input("Dose", value="500 mg")
        freq = m3.text_input("Frequency", value="twice daily")
        if st.checkbox("Include medication", key="inc_med") and med.strip():
            lines.append(entry.medication_line(med, dose, freq))

    with st.expander("Imaging study"):
        i1, i2 = st.columns([1, 2])
        modality = i1.selectbox("Modality", list(imaging.MODALITIES),
                                format_func=lambda k: imaging.MODALITIES[k])
        body_part = i2.text_input("Body part", value="Chest")
        finding = st.text_input("Reported finding", value="no acute abnormality")
        if st.checkbox("Include imaging study", key="inc_img"):
            lines.append(entry.imaging_line(modality, body_part, finding))
        st.caption("A simulated illustration of this modality will be generated for the record.")

    with st.expander("Note"):
        n1, n2 = st.columns([1, 3])
        kind = n1.selectbox("Kind", ["observation", "instruction", "allergy"])
        note = n2.text_input("Text", value="intermittent headaches")
        if st.checkbox("Include note", key="inc_note") and note.strip():
            lines.append(entry.note_line(kind, note))

    extra = st.text_area("Additional lines (one per line)", height=90,
                         placeholder="Anything else, written as it appears on a report…")
    lines += [ln for ln in extra.splitlines() if ln.strip()]

    composed = entry.compose_document(doc_title, doc_date, lines)
    st.markdown("###### This is the document that will be parsed")
    st.markdown(f'<div class="cg-src">{E(composed)}</div>', unsafe_allow_html=True)

    counts = entry.preview_counts(composed)
    p1, p2, p3 = st.columns(3)
    p1.markdown(T.metric(counts["measurements"], "measurements found"), unsafe_allow_html=True)
    p2.markdown(T.metric(counts["statements"], "statements found"), unsafe_allow_html=True)
    p3.markdown(T.metric(counts["imaging"], "imaging found"), unsafe_allow_html=True)

    if st.button("Add this record to the case", type="primary", width="stretch"):
        if not lines:
            st.error("Nothing to add — tick at least one section or write a line.")
        else:
            _set_case(entry.add_document(_state(), f"typed-{doc_date}-{len(case.documents)+1}.txt",
                                         composed, is_synthetic=True))
            st.success("Record added and the whole case re-analysed.")
            st.rerun()

st.divider()
st.caption(safety.DISCLAIMER)
