# CAREGRAPH

**A medical-record intelligence engine.** Evidence · changes · contradictions · next questions.

Built for Techfest 2026–27 SparkX, Senior Category, Generative AI track S2: HealGen.

CAREGRAPH takes several medical documents and builds a navigable, evidence-linked model
of **what changed, what conflicts, and what is missing** — instead of returning one
summary per file.

Its central question is: *what do these records collectively tell us, what can we
actually verify, and what remains uncertain?*

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then click **Load synthetic demo set** in the sidebar. No API key is needed — the
whole demo runs on a built-in deterministic generator at zero cost.

Run the tests:

```bash
python -m pytest
```

To route plain-language explanations through a real model instead:

```bash
cp .env.example .env     # add CAREGRAPH_API_KEY, then
export CAREGRAPH_API_KEY=sk-ant-...
streamlit run app.py
```

---

## What it actually does

### 1. Multi-document extraction with provenance
Ingests PDF and text records. Every extracted measurement and statement carries its
**verbatim source span** — document, page, line, character offsets. Nothing is
normalised away: if a date, unit or value is not printed in the document, it stays
`None` rather than being inferred. Scanned PDFs are detected and explained, with a
text-paste fallback.

### 2. Time machine
A faceted timeline of recorded measurements. Each analyte gets its own panel so a
value of ~7 is not flattened against a value of ~140. Hovering any point shows the
value **as printed in the source**, whether it was unit-converted, the sampling
context, and the original line of text.

### 3. Evidence graph — the signature feature
A layered, interactive graph: `documents → extracted facts → claims & flags → questions`.
Click any node to isolate it and read the source text behind it.

The graph is backed by a **verifier**, which is the safety core of the project. A claim
may only display as *supported* when:
- every evidence id it cites resolves to a real extracted fact, **and**
- every number it asserts appears in that fact's source text, **and**
- the cited records are not themselves flagged as conflicting.

Anything else is downgraded to *partially supported*, *unverified*, *conflicting
evidence*, or *insufficient information* — and shown that way, never hidden. Rejected
references are counted on the dashboard so the verifier's own behaviour is auditable.

### 4. Contradiction radar
Six cross-document checks: unit mismatches, same-day value conflicts, incomparable
sampling contexts, missing reference ranges, missing or unlabelled dates, and
conflicting medication records. Each finding shows **both source passages side by side**,
the exact reason, and what a human needs to clarify.

Findings are separated into *confirmed formatting inconsistency* and *possible factual
contradiction*. **CAREGRAPH never decides which record is correct.**

### 5. Missing-information map
Reports what is documented, what is uncertain and what is absent — undated documents,
results with no reference range, unstated sampling context, analytes measured only once.
It names the absence; it never fills it in.

### 6. Appointment copilot
Plain-language restatements, a prioritised question list anchored to real evidence, a
summary of unresolved inconsistencies, and a downloadable appointment brief.
Multiple output languages are selectable.

---

## Architecture

```
                       ┌──────────────────────────────────────────┐
  PDF / text  ────────▶│  extraction.py                           │
  uploads             │  • pdfplumber text + page/line offsets    │
                      │  • analyte, unit, reference-range parsing │
                      │  • verbatim Provenance on every fact      │
                      └───────────────┬──────────────────────────┘
                                      │  Measurement[] / Statement[]
                      ┌───────────────▼──────────────────────────┐
                      │  safety.py                               │
                      │  • prompt-injection scan + neutralise    │
                      │  • identifier redaction for logs/egress  │
                      └───────────────┬──────────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐          ┌─────────────────────┐        ┌──────────────────┐
│ timeline.py   │          │ contradictions.py   │        │ analysis.py      │
│ comparability │          │ 6 cross-doc checks  │        │ claims / gaps /  │
│ + conversion  │          │ severity split      │        │ questions /brief │
└───────┬───────┘          └──────────┬──────────┘        └────────┬─────────┘
        │                             │                            │
        └─────────────────────────────┼────────────────────────────┘
                                      ▼
                      ┌──────────────────────────────────────────┐
                      │  evidence.py   ← THE VERIFIER            │
                      │  • reject ids that match no real fact    │
                      │  • reject numbers absent from the source │
                      │  • conflicting evidence outranks a match │
                      │  • build graph; drop any dangling edge   │
                      └───────────────┬──────────────────────────┘
                                      │ Case (fully validated)
                      ┌───────────────▼──────────────────────────┐
                      │  app.py + viz.py + ui_theme.py           │
                      │  6-tab dashboard, Plotly, click-to-focus │
                      └──────────────────────────────────────────┘

  llm.py sits beside analysis.py: OfflineProvider (default, deterministic, free)
  or AnthropicProvider, both wrapped in ResilientProvider. Model output is parsed
  into a Pydantic schema, stripped of any evidence id it was not given, and then
  sent through the same verifier as everything else.
```

### Data flow in one sentence
Bytes → text with offsets → validated facts with provenance → cross-document checks →
generated claims → **verification against real sources** → graph, charts and brief.

The model never decides what is true. It only rephrases facts the deterministic
pipeline already extracted and verified.

### Module map

| File | Responsibility |
|---|---|
| `caregraph/schemas.py` | Pydantic models. Extracted facts and generated claims are separate types. |
| `caregraph/extraction.py` | PDF/text ingestion, analyte/unit/range parsing, provenance. |
| `caregraph/units.py` | Analyte vocabulary, unit canonicalisation, safe conversions only. |
| `caregraph/safety.py` | Injection scanning, neutralisation, redaction, disclaimer. |
| `caregraph/timeline.py` | Comparable series, conversions, explicit exclusions. |
| `caregraph/contradictions.py` | The six cross-document checks. |
| `caregraph/evidence.py` | Claim verification, evidence graph, integrity report. |
| `caregraph/analysis.py` | Claims, gaps, prioritised questions, appointment brief. |
| `caregraph/llm.py` | Provider adapter, schema validation, retry and fallback. |
| `caregraph/viz.py` | Plotly figures, layered graph layout. |
| `caregraph/ui_theme.py` | Single source of colour and CSS. |
| `app.py` | Streamlit dashboard. |

---

## Safety and privacy

- **Documents are untrusted data, never instructions.** Model-directed text inside an
  upload is detected, labelled in the UI, and fenced + neutralised before any prompt is
  built. The demo set contains a real injection attempt that tells the system to report
  everything as normal and suppress all flags — it is caught and ignored.
- **No retention.** Documents live in Streamlit session state for the session only.
  Nothing is written to disk.
- **No sensitive logging.** Error paths pass through `safe_log()`, which redacts names,
  IDs, emails and phone numbers and truncates.
- **Keys from the environment only.** Never in source, never in browser code.
- **Synthetic demo data**, clearly labelled as simulated in the UI and in the exported brief.
- **Not a medical device.** The app does not diagnose, prescribe or recommend treatment
  changes. The disclaimer is shown on every screen and in every export.

---

## Testing

```
$ python -m pytest
```

**83 tests, all passing.** Coverage by area:

| Area | What is tested |
|---|---|
| Extraction | multi-document ingest, provenance verbatim, units, ranges, BP splitting, missing/unlabelled dates |
| PDF | a real byte-level PDF is built in `conftest.py` and parsed; truncated PDFs; no-text-layer PDFs |
| Robustness | empty input, oversized input, 5 000-line input, non-UTF-8 bytes, malformed PDF |
| Verifier | nonexistent ids rejected, dangling refs downgraded, hallucinated numbers caught, uncited claims unverified, no dangling graph edges |
| Contradictions | incompatible vs convertible units, same-day conflicts, tolerance, missing ranges/dates, dose changes, no false positives on a clean document |
| LLM adapter | invalid JSON, schema violations, timeout, rate limit, connection failure, retry-then-give-up, fallback to offline, **model cannot widen its own evidence set**, injection fenced in the prompt, errors redacted |
| Privacy | identifier redaction, log truncation |
| Pipeline | determinism, **demo answers are not hardcoded**, non-convertible units excluded, missing ≠ zero, brief contains no diagnosis |

Two tests are worth singling out:

- `test_demo_set_is_not_hardcoded` edits a sample value in memory, re-runs the whole
  pipeline, and asserts the findings change — proving the output is computed, not canned.
- `test_model_cannot_widen_its_own_evidence_set` feeds a fake model response citing an
  invented evidence id and asserts it is stripped.

---

## Bill of materials and cost

Prototype budget: **₹5,000**. Actual spend: **₹0**.

| Item | Choice | Cost |
|---|---|---|
| Language / runtime | Python 3.10+ | ₹0 (open source) |
| UI framework | Streamlit | ₹0 |
| Validation | Pydantic v2 | ₹0 |
| PDF extraction | pdfplumber | ₹0 |
| Charts & graph | Plotly | ₹0 |
| Testing | pytest | ₹0 |
| AI inference | Built-in deterministic generator | ₹0 |
| Demo data | Self-authored synthetic records | ₹0 |
| Hosting for the demo | Runs locally on the presenting laptop | ₹0 |
| **Total committed** | | **₹0** |

Optional, only if a live API is demonstrated: Claude API usage for the explanation
feature is a few hundred tokens per click, well under **₹100** for an entire event —
leaving over ₹4,900 of headroom. The system is deliberately architected so this is an
enhancement, not a dependency: pull the key and everything still works.

---

## What is genuinely novel, and what is not

**Honest framing: CAREGRAPH is a strong product direction, not a research breakthrough.**
Clinical-documentation tools, FHIR timeline viewers and RAG-with-citations systems all
exist. We are not claiming to have invented cross-document reasoning.

**What is actually implemented and does differ from a generic report summariser:**

1. **A verifier that can reject its own system's output.** Most "cited AI" shows a
   citation next to a sentence. CAREGRAPH checks that the citation resolves to a real
   extracted fact *and* that the numbers in the sentence appear in that fact's source
   text, then publishes the rejection count on the dashboard. Claims that fail are
   downgraded in the UI rather than quietly dropped.
2. **Refusing to plot.** The system knows which units it cannot safely convert. HbA1c in
   `mmol/mol` is held out of a `%` chart with the reason shown, instead of being rendered
   as a catastrophic spike. Most dashboards plot whatever parses.
3. **Severity separation in contradiction detection.** A formatting inconsistency and a
   possible factual contradiction are different claims about the world, and are never
   merged — and neither is ever auto-resolved.
4. **Absence as a first-class output.** The missing-information map treats "not recorded"
   as a finding, not a blank.
5. **The LLM is downstream of truth, not upstream of it.** Extraction, comparison and
   contradiction detection are deterministic. The model only rephrases. That is why the
   demo is reproducible and costs nothing.

**Current limitations, stated plainly:**

- Extraction is regex- and vocabulary-driven. It handles the common `analyte: value unit
  (range)` layouts well; complex multi-column lab tables and handwritten notes are out of
  scope.
- The analyte vocabulary covers ~17 common markers. Unrecognised analytes are ignored
  rather than guessed at.
- No OCR, so scanned PDFs are detected and routed to the text-paste fallback.
- Date parsing handles four common formats; `03/04/2025` is read as D/M/Y.
- Contradiction detection is rule-based, so it finds the classes of problem it was
  designed for and does not claim to find everything.
- Translation quality in the offline mode is structural, not fluent — real multilingual
  phrasing requires a configured API key.

We would want to benchmark against existing clinical-documentation tooling before making
any novelty claim stronger than the above.

---

## Live demo script (2 minutes)

**0:00 — The problem (15s)**
> "Three reports from three labs over nine months. Summarising each one separately tells
> you nothing about what changed between them, or where they disagree. That's the gap."

**0:15 — Load and process (20s)**
Click **Load synthetic demo set**. Point at the metric row.
> "Four documents, 33 extracted facts, 23 generated claims — and every one of those facts
> keeps the exact line of text it came from."

Point at the amber banner.
> "One of these documents contains a line telling the AI to report everything as normal
> and suppress all warnings. We detected it, labelled it, and treated it as data. It had
> no effect — you'll see the flags in a moment."

**0:35 — Timeline (25s)**
Open **Timeline**.
> "Glucose jumps vertically on the same date — two documents, two different values for
> January 20th."

Scroll to the held-out card.
> "And here's the part I'm proudest of. One lab reported HbA1c in mmol/mol instead of
> percent. There's no plain conversion factor between them, so instead of drawing a
> spike from 6.9 to 53 — which is what most dashboards would do — CAREGRAPH refuses to
> plot it and tells you exactly why."

**1:00 — Evidence graph (30s)**
Open **Evidence graph**.
> "Documents on the left, extracted facts in the middle, claims and flags on the right."

Click a claim node.
> "Click anything and you get the original source text, with filename, page and line."

Point at the status bar and the green verifier box.
> "Every claim is checked: does its citation resolve to a real fact, and do its numbers
> actually appear in that source? Thirteen supported, eight only partially, two sitting
> on conflicting records. Nothing is presented as more certain than its evidence."

**1:30 — Radar and brief (25s)**
Open **Contradiction radar**.
> "Both passages side by side, the exact reason, and what a human needs to clarify. Note
> it never says which record is right — that's not ours to decide."

Open **Appointment brief**, click download.
> "And it ends as something you can actually use: prioritised questions, every one
> anchored to real evidence, in a brief you can take to your appointment."

**1:55 — Close (5s)**
> "Deterministic, reproducible, zero API cost, 83 passing tests. Thank you."
