"""Analyte vocabulary and unit handling.

Conversions are deliberately conservative: we only convert where a single,
universally agreed factor exists. Anything else is reported as incomparable
rather than silently converted.
"""
from __future__ import annotations

# analyte key -> (canonical display, accepted printed aliases)
ANALYTES: dict[str, tuple[str, tuple[str, ...]]] = {
    "hba1c": ("HbA1c", ("hba1c", "hb a1c", "glycated haemoglobin", "glycated hemoglobin", "a1c")),
    "glucose_fasting": ("Fasting glucose", ("fasting glucose", "fasting blood glucose", "fbs", "fasting plasma glucose")),
    "glucose_random": ("Random glucose", ("random glucose", "random blood sugar", "rbs")),
    "ldl": ("LDL cholesterol", ("ldl cholesterol", "ldl-c", "ldl")),
    "hdl": ("HDL cholesterol", ("hdl cholesterol", "hdl-c", "hdl")),
    "total_cholesterol": ("Total cholesterol", ("total cholesterol", "cholesterol total", "serum cholesterol")),
    "triglycerides": ("Triglycerides", ("triglycerides", "tg", "serum triglycerides")),
    "creatinine": ("Creatinine", ("creatinine", "serum creatinine")),
    "egfr": ("eGFR", ("egfr", "estimated gfr")),
    "haemoglobin": ("Haemoglobin", ("haemoglobin", "hemoglobin", "hb")),
    "tsh": ("TSH", ("tsh", "thyroid stimulating hormone")),
    "vitamin_d": ("Vitamin D", ("vitamin d", "25-oh vitamin d", "25(oh)d")),
    "alt": ("ALT", ("alt", "sgpt", "alanine aminotransferase")),
    "weight": ("Weight", ("weight", "body weight")),
    "bmi": ("BMI", ("bmi", "body mass index")),
    "bp_systolic": ("Systolic BP", ("systolic bp", "systolic blood pressure", "systolic")),
    "bp_diastolic": ("Diastolic BP", ("diastolic bp", "diastolic blood pressure", "diastolic")),
}

# printed unit -> canonical unit token
UNIT_ALIASES: dict[str, str] = {
    "%": "%", "percent": "%",
    "mg/dl": "mg/dL", "mg/dl.": "mg/dL", "mgdl": "mg/dL",
    "mmol/l": "mmol/L", "mmol/liter": "mmol/L",
    "g/dl": "g/dL", "g/l": "g/L",
    "mmhg": "mmHg", "mm hg": "mmHg",
    "kg": "kg", "lb": "lb", "lbs": "lb",
    "miu/l": "mIU/L", "uiu/ml": "mIU/L", "µiu/ml": "mIU/L",
    "ng/ml": "ng/mL", "nmol/l": "nmol/L",
    "u/l": "U/L", "iu/l": "U/L",
    "umol/l": "umol/L", "µmol/l": "umol/L",
    "ml/min/1.73m2": "mL/min/1.73m2", "ml/min": "mL/min",
    "kg/m2": "kg/m2", "kg/m²": "kg/m2",
    "mmol/mol": "mmol/mol",
}

# (analyte, from_unit, to_unit) -> multiplicative factor
CONVERSIONS: dict[tuple[str, str, str], float] = {
    ("glucose_fasting", "mmol/L", "mg/dL"): 18.016,
    ("glucose_random", "mmol/L", "mg/dL"): 18.016,
    ("ldl", "mmol/L", "mg/dL"): 38.67,
    ("hdl", "mmol/L", "mg/dL"): 38.67,
    ("total_cholesterol", "mmol/L", "mg/dL"): 38.67,
    ("triglycerides", "mmol/L", "mg/dL"): 88.57,
    ("creatinine", "umol/L", "mg/dL"): 1 / 88.4,
    ("weight", "lb", "kg"): 0.45359237,
}

# the unit each analyte is plotted in when a conversion exists
PREFERRED_UNIT: dict[str, str] = {
    "glucose_fasting": "mg/dL", "glucose_random": "mg/dL", "ldl": "mg/dL",
    "hdl": "mg/dL", "total_cholesterol": "mg/dL", "triglycerides": "mg/dL",
    "creatinine": "mg/dL", "weight": "kg",
}

# Units that must never be silently converted even though both appear in the wild.
# HbA1c %/mmol-per-mol uses a derived IFCC equation, not a plain factor, so we
# flag it for human review instead of plotting the two together.
NON_CONVERTIBLE: set[tuple[str, str, str]] = {
    ("hba1c", "%", "mmol/mol"),
    ("hba1c", "mmol/mol", "%"),
}


def canonical_unit(printed: str | None) -> str | None:
    if not printed:
        return None
    key = printed.strip().lower().replace(" ", "")
    for alias, canon in UNIT_ALIASES.items():
        if alias.replace(" ", "") == key:
            return canon
    return printed.strip()


def analyte_key(printed_name: str) -> str | None:
    """Map a printed label to an analyte key, longest alias first."""
    name = printed_name.strip().lower().strip(":-. ")
    best: tuple[int, str] | None = None
    for key, (_display, aliases) in ANALYTES.items():
        for alias in aliases:
            if name == alias or name.startswith(alias + " ") or name.endswith(" " + alias):
                if best is None or len(alias) > best[0]:
                    best = (len(alias), key)
    return best[1] if best else None


def display_for(key: str) -> str:
    return ANALYTES[key][0] if key in ANALYTES else key


def convert(analyte: str, value: float, from_unit: str, to_unit: str) -> float | None:
    """Return converted value, or None when no safe conversion is defined."""
    if from_unit == to_unit:
        return value
    if (analyte, from_unit, to_unit) in NON_CONVERTIBLE:
        return None
    factor = CONVERSIONS.get((analyte, from_unit, to_unit))
    if factor is not None:
        return value * factor
    inverse = CONVERSIONS.get((analyte, to_unit, from_unit))
    if inverse:
        return value / inverse
    return None


def comparable(analyte: str, unit_a: str | None, unit_b: str | None) -> bool:
    if unit_a == unit_b:
        return True
    if unit_a is None or unit_b is None:
        return False
    return convert(analyte, 1.0, unit_a, unit_b) is not None
