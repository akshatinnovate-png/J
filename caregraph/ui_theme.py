"""Visual language for CAREGRAPH. One place for every colour the app uses."""

BG = "#070d1a"
SURFACE = "#0e1726"
SURFACE_2 = "#152133"
BORDER = "#1f2e45"
TEXT = "#e8eef7"
MUTED = "#8da0bd"
CYAN = "#22d3ee"
TEAL = "#14b8a6"
AMBER = "#f5a524"
ROSE = "#f43f5e"
VIOLET = "#a78bfa"
GREEN = "#34d399"

STATUS_COLOR = {
    "supported": GREEN,
    "partially_supported": AMBER,
    "unverified": MUTED,
    "conflicting_evidence": ROSE,
    "insufficient_information": VIOLET,
}

STATUS_LABEL = {
    "supported": "Supported by source",
    "partially_supported": "Partially supported",
    "unverified": "Unverified",
    "conflicting_evidence": "Conflicting evidence",
    "insufficient_information": "Insufficient information",
}

NODE_COLOR = {
    "document": CYAN,
    "fact": TEAL,
    "claim": GREEN,
    "flag": ROSE,
    "question": VIOLET,
}

# A colourblind-safe sequence for timeline series.
SERIES_COLORS = [CYAN, AMBER, VIOLET, GREEN, "#60a5fa", "#fb7185", "#facc15", "#2dd4bf"]

CSS = f"""
<style>
.stApp {{ background: {BG}; }}
section.main > div {{ padding-top: 1.2rem; }}
h1, h2, h3, h4 {{ color: {TEXT}; letter-spacing: -0.02em; }}
p, li, span, label {{ color: {TEXT}; }}
.cg-hero {{
  background: linear-gradient(135deg, {SURFACE} 0%, #0b1424 60%, #0a1b24 100%);
  border: 1px solid {BORDER}; border-radius: 18px; padding: 26px 30px; margin-bottom: 18px;
}}
.cg-hero h1 {{ font-size: 2.35rem; margin: 0 0 6px 0; }}
.cg-hero .sub {{ color: {MUTED}; font-size: 1.02rem; margin: 0; }}
.cg-tag {{
  display:inline-block; padding: 3px 11px; border-radius: 999px; font-size: 0.74rem;
  font-weight: 600; letter-spacing: .04em; text-transform: uppercase; margin-right: 6px;
}}
.cg-card {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px;
  padding: 16px 18px; margin-bottom: 12px;
}}
.cg-card.flagged {{ border-left: 3px solid {AMBER}; }}
.cg-card.conflict {{ border-left: 3px solid {ROSE}; }}
.cg-src {{
  background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px;
  padding: 11px 13px; font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 0.82rem; color: {TEXT}; white-space: pre-wrap; word-break: break-word;
}}
.cg-metric {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px;
  padding: 14px 16px; text-align: left;
}}
.cg-metric .v {{ font-size: 1.85rem; font-weight: 700; color: {CYAN}; line-height: 1.1; }}
.cg-metric .k {{ font-size: 0.76rem; color: {MUTED}; text-transform: uppercase; letter-spacing: .06em; }}
.cg-muted {{ color: {MUTED}; font-size: 0.86rem; }}
.cg-empty {{
  border: 1px dashed {BORDER}; border-radius: 14px; padding: 34px; text-align: center;
  color: {MUTED};
}}
.stTabs [role="tablist"] {{ gap: 4px; border-bottom: 1px solid {BORDER}; }}
.stTabs [role="tab"] {{
  background: transparent; color: {MUTED}; border-radius: 9px 9px 0 0; padding: 9px 17px;
}}
.stTabs [aria-selected="true"] {{ background: {SURFACE}; color: {CYAN}; }}
div[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
.stButton button {{
  background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 10px;
}}
.stButton button:hover {{ border-color: {CYAN}; color: {CYAN}; }}
@media (max-width: 760px) {{ .cg-hero h1 {{ font-size: 1.6rem; }} }}
</style>
"""


def tag(text: str, color: str) -> str:
    return f'<span class="cg-tag" style="background:{color}22;color:{color};border:1px solid {color}55">{text}</span>'


def metric(value: object, key: str) -> str:
    return f'<div class="cg-metric"><div class="v">{value}</div><div class="k">{key}</div></div>'
