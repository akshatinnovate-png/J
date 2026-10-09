"""Visual language for CAREGRAPH. One place for every colour the app uses.

Light, clinical and high-contrast: a near-white canvas, one blue accent, and
colour reserved for meaning (evidence status, flag severity) rather than decoration.
"""

BG = "#F4F6F8"
CANVAS = "#FFFFFF"
SURFACE = "#FFFFFF"
SURFACE_2 = "#F7F9FB"
BORDER = "#E3E8EF"
BORDER_STRONG = "#CBD5E1"
INK = "#0F172A"
TEXT = "#1E293B"
MUTED = "#64748B"
FAINT = "#94A3B8"

BLUE = "#2563EB"
BLUE_SOFT = "#DBEAFE"
CYAN = "#0891B2"
TEAL = "#0D9488"
AMBER = "#D97706"
AMBER_SOFT = "#FEF3C7"
ROSE = "#E11D48"
ROSE_SOFT = "#FFE4E6"
VIOLET = "#7C3AED"
GREEN = "#059669"
GREEN_SOFT = "#D1FAE5"

STATUS_COLOR = {
    "supported": GREEN,
    "partially_supported": AMBER,
    "unverified": MUTED,
    "conflicting_evidence": ROSE,
    "insufficient_information": VIOLET,
}
STATUS_SOFT = {
    "supported": GREEN_SOFT,
    "partially_supported": AMBER_SOFT,
    "unverified": "#F1F5F9",
    "conflicting_evidence": ROSE_SOFT,
    "insufficient_information": "#EDE9FE",
}
STATUS_LABEL = {
    "supported": "Supported by source",
    "partially_supported": "Partially supported",
    "unverified": "Unverified",
    "conflicting_evidence": "Conflicting evidence",
    "insufficient_information": "Insufficient information",
}

NODE_COLOR = {
    "document": BLUE,
    "fact": TEAL,
    "claim": GREEN,
    "flag": ROSE,
    "question": VIOLET,
}

# Category colours for the care-flow canvas.
CATEGORY = {
    "Docs": BLUE,
    "Labs": TEAL,
    "Imaging": VIOLET,
    "Medications": AMBER,
    "Visits": CYAN,
    "Findings": ROSE,
}

SERIES_COLORS = [BLUE, AMBER, TEAL, VIOLET, "#DB2777", "#65A30D", "#0EA5E9", "#F97316"]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.stApp {{ background: {BG}; }}
html, body, [class*="st-"] {{ font-family: Inter, system-ui, -apple-system, sans-serif; }}
h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.021em; font-weight: 650; }}
p, li, span, label {{ color: {TEXT}; }}

.cg-hero {{
  background: {CANVAS}; border: 1px solid {BORDER}; border-radius: 20px;
  padding: 24px 28px; margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px -12px rgba(15,23,42,.10);
}}
.cg-hero h1 {{
  font-size: 1.95rem; margin: 0 0 4px 0; font-weight: 700; letter-spacing: -0.03em;
}}
.cg-hero .sub {{ color: {MUTED}; font-size: .97rem; margin: 0; }}

.cg-tag {{
  display:inline-block; padding: 4px 11px; border-radius: 999px; font-size: .715rem;
  font-weight: 600; letter-spacing: .035em; text-transform: uppercase; margin: 2px 5px 2px 0;
}}
.cg-card {{
  background: {CANVAS}; border: 1px solid {BORDER}; border-radius: 14px;
  padding: 15px 17px; margin-bottom: 11px;
  box-shadow: 0 1px 2px rgba(15,23,42,.04);
}}
.cg-card.flagged {{ border-left: 3px solid {AMBER}; }}
.cg-card.conflict {{ border-left: 3px solid {ROSE}; }}
.cg-src {{
  background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 9px;
  padding: 10px 12px; font-family: "SF Mono", ui-monospace, Menlo, monospace;
  font-size: .79rem; color: {INK}; white-space: pre-wrap; word-break: break-word;
}}
.cg-metric {{
  background: {CANVAS}; border: 1px solid {BORDER}; border-radius: 14px;
  padding: 13px 15px; box-shadow: 0 1px 2px rgba(15,23,42,.04);
}}
.cg-metric .v {{ font-size: 1.7rem; font-weight: 700; color: {INK}; line-height: 1.12;
                 letter-spacing: -0.03em; }}
.cg-metric .k {{ font-size: .695rem; color: {MUTED}; text-transform: uppercase;
                 letter-spacing: .07em; font-weight: 600; margin-top: 2px; }}
.cg-muted {{ color: {MUTED}; font-size: .85rem; }}
.cg-empty {{
  border: 1px dashed {BORDER_STRONG}; border-radius: 16px; padding: 38px; text-align: center;
  color: {MUTED}; background: {CANVAS};
}}

/* care-team / condition rail */
.cg-rail {{
  background: {CANVAS}; border: 1px solid {BORDER}; border-radius: 16px;
  padding: 6px; box-shadow: 0 1px 2px rgba(15,23,42,.04);
}}
.cg-person {{
  display:flex; align-items:center; gap:11px; padding: 9px 11px; border-radius: 11px;
}}
.cg-person:hover {{ background: {SURFACE_2}; }}
.cg-person .av {{
  width: 32px; height: 32px; border-radius: 50%; background: {BLUE_SOFT}; color: {BLUE};
  display:flex; align-items:center; justify-content:center; font-weight:650; font-size:.76rem;
  flex: 0 0 32px;
}}
.cg-person .nm {{ font-size: .855rem; font-weight: 600; color: {INK}; line-height:1.25; }}
.cg-person .ro {{ font-size: .745rem; color: {MUTED}; }}
.cg-person .ct {{
  margin-left:auto; background:{SURFACE_2}; color:{MUTED}; border-radius:999px;
  padding:1px 8px; font-size:.72rem; font-weight:600;
}}
.cg-condition {{
  background: {INK}; border-radius: 16px; padding: 17px 19px; color: #fff; margin-bottom: 11px;
}}
.cg-condition .lbl {{ font-size:.70rem; text-transform:uppercase; letter-spacing:.08em;
                      color:#94A3B8; font-weight:600; }}
.cg-condition .nm {{ font-size:1.22rem; font-weight:680; margin-top:5px; line-height:1.22;
                     letter-spacing:-.02em; }}
.cg-condition .mk {{ font-size:.78rem; color:#CBD5E1; margin-top:7px; }}

.cg-scan {{
  border-radius: 12px; border: 1px solid {BORDER}; overflow: hidden; background: #000;
}}
.cg-simbadge {{
  display:inline-block; background:{ROSE_SOFT}; color:{ROSE}; border:1px solid {ROSE}33;
  border-radius:6px; padding:2px 8px; font-size:.70rem; font-weight:650;
  letter-spacing:.03em;
}}

.stTabs [role="tablist"] {{ gap: 3px; border-bottom: 1px solid {BORDER}; }}
.stTabs [role="tab"] {{
  background: transparent; color: {MUTED}; border-radius: 10px 10px 0 0; padding: 9px 16px;
  font-weight: 550; font-size: .90rem;
}}
.stTabs [aria-selected="true"] {{ background: {CANVAS}; color: {BLUE}; font-weight: 640; }}

div[data-testid="stSidebar"] {{ background: {CANVAS}; border-right: 1px solid {BORDER}; }}
.stButton button {{
  background: {CANVAS}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 10px;
  font-weight: 550;
}}
.stButton button:hover {{ border-color: {BLUE}; color: {BLUE}; background: {SURFACE_2}; }}
.stButton button[kind="primary"] {{ background: {INK}; color: #fff; border-color: {INK}; }}
.stButton button[kind="primary"]:hover {{ background: {BLUE}; border-color: {BLUE}; color:#fff; }}
div[data-testid="stMetricValue"] {{ color: {INK}; }}

@media (max-width: 760px) {{
  .cg-hero h1 {{ font-size: 1.45rem; }}
  .cg-hero {{ padding: 18px 18px; }}
}}
</style>
"""


def tag(text: str, color: str, soft: str | None = None) -> str:
    bg = soft or f"{color}14"
    return (f'<span class="cg-tag" style="background:{bg};color:{color};'
            f'border:1px solid {color}33">{text}</span>')


def metric(value: object, key: str) -> str:
    return f'<div class="cg-metric"><div class="v">{value}</div><div class="k">{key}</div></div>'


def person_row(initials: str, name: str, role: str, count: int | None = None) -> str:
    badge = f'<span class="ct">{count}</span>' if count is not None else ""
    return (f'<div class="cg-person"><div class="av">{initials}</div>'
            f'<div><div class="nm">{name}</div><div class="ro">{role}</div></div>{badge}</div>')
