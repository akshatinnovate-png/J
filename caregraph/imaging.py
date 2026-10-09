"""Procedurally generated synthetic medical imaging.

Nothing here is a real patient study. Every image is drawn from scratch with
numpy and PIL from a deterministic seed, and every image carries a SIMULATED
watermark burned into the pixels so a generated study cannot be mistaken for a
genuine one once it leaves the interface.

Studies are generated at request time and never written to disk.
"""
from __future__ import annotations

import base64
import hashlib
import io
import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

MODALITIES = {
    "xray_chest": "X-ray · Chest PA",
    "mri_brain": "MRI · Brain axial T2",
    "ultrasound_cardiac": "Ultrasound · Cardiac 4-chamber",
    "ct_abdomen": "CT · Abdomen axial",
    "ecg": "ECG · 12-lead rhythm strip",
}


@dataclass
class Study:
    study_id: str
    modality: str
    label: str
    seed: int
    width: int = 420
    height: int = 420
    findings: list[str] = field(default_factory=list)
    measurements: dict[str, str] = field(default_factory=dict)

    @property
    def modality_label(self) -> str:
        return MODALITIES.get(self.modality, self.modality)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _grain(w: int, h: int, rng: np.random.Generator, scale: float = 1.0) -> np.ndarray:
    """Correlated grain: smooth low-frequency mottle plus fine sensor noise."""
    coarse = rng.normal(0, 1, (max(h // 8, 2), max(w // 8, 2)))
    coarse_img = Image.fromarray(((coarse - coarse.min()) /
                                  (np.ptp(coarse) + 1e-9) * 255).astype(np.uint8))
    coarse_up = np.asarray(coarse_img.resize((w, h), Image.BICUBIC), dtype=np.float32)
    coarse_up = (coarse_up / 255.0 - 0.5) * 2
    fine = rng.normal(0, 1, (h, w))
    return (coarse_up * 0.65 + fine * 0.35) * scale


def _vignette(w: int, h: int, strength: float = 0.45) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w / 2, h / 2
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    return np.clip(1.0 - strength * np.clip(r - 0.45, 0, None) ** 1.6, 0, 1)


def _ellipse_mask(w: int, h: int, cx: float, cy: float, rx: float, ry: float,
                  rot: float = 0.0, feather: float = 0.0) -> np.ndarray:
    """Soft-edged ellipse in [0,1]."""
    yy, xx = np.mgrid[0:h, 0:w]
    x = xx - cx
    y = yy - cy
    if rot:
        ca, sa = math.cos(rot), math.sin(rot)
        x, y = x * ca + y * sa, -x * sa + y * ca
    d = np.sqrt((x / max(rx, 1e-6)) ** 2 + (y / max(ry, 1e-6)) ** 2)
    if feather <= 0:
        return (d <= 1.0).astype(np.float32)
    return np.clip((1.0 - d) / feather + 1.0, 0, 1).astype(np.float32)


def _soft(w: int, h: int, blur: float, draw_fn) -> np.ndarray:
    """Draw with PIL then blur, returning a float field in [0,255]."""
    layer = Image.new("L", (w, h), 0)
    draw_fn(ImageDraw.Draw(layer))
    return np.asarray(layer.filter(ImageFilter.GaussianBlur(blur)), dtype=np.float32)


def _annulus(w: int, h: int, cx: float, cy: float, rx: float, ry: float,
             thickness: float, rot: float = 0.0, feather: float = 0.18) -> np.ndarray:
    """Soft ring between two concentric ellipses - a tissue wall, not a drawn line."""
    outer = _ellipse_mask(w, h, cx, cy, rx, ry, rot=rot, feather=feather)
    inner = _ellipse_mask(w, h, cx, cy, max(rx - thickness, 1.0),
                          max(ry - thickness, 1.0), rot=rot, feather=feather)
    return np.clip(outer - inner, 0, 1)


def _arc_band(w: int, h: int, box, start: float, end: float,
              width: int, value: int, blur: float) -> np.ndarray:
    """A single soft anatomical arc (rib, diaphragm) with a gaussian cross-section."""
    return _soft(w, h, blur, lambda d: d.arc(box, start=start, end=end,
                                             fill=value, width=width))


def _to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")


# --------------------------------------------------------------- chest X-ray
def _chest_xray(study: Study) -> Image.Image:
    """Modelled as X-ray attenuation: air is dark, soft tissue mid, bone bright."""
    w, h = study.width, study.height
    rng = _rng(study.seed)

    img = np.full((h, w), 6.0, dtype=np.float32)

    # thorax soft-tissue envelope
    body = _ellipse_mask(w, h, w * 0.5, h * 0.55, w * 0.405, h * 0.475, feather=0.09)
    shoulders = _ellipse_mask(w, h, w * 0.5, h * 0.185, w * 0.455, h * 0.175, feather=0.28)
    soft = np.clip(body + shoulders * 0.9, 0, 1)
    img += soft * 74

    # lung fields are air: they attenuate least, so they read darkest
    lung_l = _ellipse_mask(w, h, w * 0.337, h * 0.495, w * 0.152, h * 0.272, rot=0.09, feather=0.20)
    lung_r = _ellipse_mask(w, h, w * 0.663, h * 0.495, w * 0.152, h * 0.272, rot=-0.09, feather=0.20)
    # clip the lower-medial corner where the heart sits
    heart = _ellipse_mask(w, h, w * 0.455, h * 0.585, w * 0.150, h * 0.185, rot=0.26, feather=0.30)
    lungs = np.clip(lung_l + lung_r, 0, 1) * (1 - heart * 0.85)
    img *= (1 - lungs * 0.82)

    # pulmonary vessels fan out from each hilum and taper peripherally
    def vessels(d):
        for side in (-1, 1):
            hx, hy = w * (0.5 + side * 0.075), h * 0.49
            for _ in range(22):
                ang = math.pi / 2 + rng.uniform(-1.15, 1.15)
                x, y, bright = hx, hy, rng.uniform(120, 215)
                width = rng.uniform(2.6, 4.4)
                pts = [(x, y)]
                for _step in range(rng.integers(5, 13)):
                    ang += rng.normal(0, 0.26)
                    x += math.cos(ang) * 7 * side
                    y += math.sin(ang) * 7
                    pts.append((x, y))
                for i in range(len(pts) - 1):
                    taper = max(width * (1 - i / max(len(pts) - 1, 1)), 1)
                    d.line([pts[i], pts[i + 1]],
                           fill=int(bright * (1 - i / (len(pts) + 2))), width=int(taper))
    img += _soft(w, h, 1.3, vessels) * 0.45 * lungs

    # posterior ribs: broad, soft, descending laterally
    ribs = np.zeros((h, w), dtype=np.float32)
    for i in range(9):
        y0 = h * (0.225 + i * 0.0585)
        spread = w * (0.20 + i * 0.0175)
        drop = h * (0.10 + i * 0.013)
        bright = int(168 - i * 7)
        for side in (-1, 1):
            if side < 0:
                box = [w * 0.5 - spread, y0 - drop, w * 0.5 + w * 0.03, y0 + drop]
            else:
                box = [w * 0.5 - w * 0.03, y0 - drop, w * 0.5 + spread, y0 + drop]
            ribs += _arc_band(w, h, box, 195, 345, 7, bright, 2.3)
    # anterior ribs: lower, shallower, fainter
    for i in range(6):
        y0 = h * (0.345 + i * 0.062)
        spread = w * (0.185 + i * 0.016)
        for side in (-1, 1):
            if side < 0:
                box = [w * 0.5 - spread, y0 - h * 0.05, w * 0.5, y0 + h * 0.135]
            else:
                box = [w * 0.5, y0 - h * 0.05, w * 0.5 + spread, y0 + h * 0.135]
            ribs += _arc_band(w, h, box, 205, 335, 5, 92 - i * 6, 2.8)
    # ribs attenuate more where they cross air than where they cross soft tissue
    img += ribs * (0.30 + 0.26 * lungs) * np.clip(soft + 0.15, 0, 1)

    # clavicles
    img += _arc_band(w, h, [w * 0.15, h * 0.155, w * 0.505, h * 0.295], 200, 340, 8, 200, 2.2) * 0.42
    img += _arc_band(w, h, [w * 0.495, h * 0.155, w * 0.85, h * 0.295], 200, 340, 8, 200, 2.2) * 0.42

    # mediastinum, spine and vertebral bodies - all confined to the thorax
    img += _ellipse_mask(w, h, w * 0.5, h * 0.44, w * 0.052, h * 0.26, feather=0.30) * 26 * soft
    spine = _ellipse_mask(w, h, w * 0.5, h * 0.54, w * 0.038, h * 0.42, feather=0.22)
    img += spine * 24 * soft
    def verts(d):
        for i in range(12):
            y = h * (0.205 + i * 0.0495)
            d.rounded_rectangle([w * 0.466, y, w * 0.534, y + h * 0.034],
                                radius=3, fill=58)
    img += _soft(w, h, 1.8, verts) * 0.32 * soft

    # cardiac silhouette and great vessels
    img += heart * 34 * soft
    img += _ellipse_mask(w, h, w * 0.552, h * 0.385, w * 0.048, h * 0.042, feather=0.40) * 24 * soft
    img += _ellipse_mask(w, h, w * 0.47, h * 0.33, w * 0.030, h * 0.090, feather=0.5) * 16 * soft

    # diaphragm domes, with the right dome sitting higher
    img += _soft(w, h, 3.0, lambda d: (
        d.pieslice([w * 0.17, h * 0.600, w * 0.515, h * 0.96], 180, 360, fill=112),
        d.pieslice([w * 0.485, h * 0.640, w * 0.82, h * 1.00], 180, 360, fill=100))) * 0.42 * soft
    img += _ellipse_mask(w, h, w * 0.5, h * 0.98, w * 0.40, h * 0.17, feather=0.28) * 44 * soft

    # gastric air bubble under the left dome
    img -= _ellipse_mask(w, h, w * 0.615, h * 0.80, w * 0.055, h * 0.038, feather=0.35) * 34

    img += _grain(w, h, rng, 6.0)
    img *= _vignette(w, h, 0.46)
    return _to_image(img).filter(ImageFilter.GaussianBlur(0.6))


# ------------------------------------------------------------------ brain MRI
def _brain_mri(study: Study) -> Image.Image:
    """Axial T2: CSF bright, grey matter mid, white matter darker than grey."""
    w, h = study.width, study.height
    rng = _rng(study.seed)
    img = np.full((h, w), 5.0, dtype=np.float32)

    cx, cy = w * 0.5, h * 0.5
    rx, ry = w * 0.355, h * 0.425

    scalp = _ellipse_mask(w, h, cx, cy, rx * 1.085, ry * 1.070, feather=0.035)
    outer_skull = _ellipse_mask(w, h, cx, cy, rx * 1.030, ry * 1.018, feather=0.030)
    inner_skull = _ellipse_mask(w, h, cx, cy, rx * 0.975, ry * 0.962, feather=0.028)
    brain = _ellipse_mask(w, h, cx, cy, rx * 0.945, ry * 0.930, feather=0.030)

    img += (scalp - outer_skull) * 120                 # subcutaneous fat
    img += (outer_skull - inner_skull) * 14            # cortical bone, very dark
    img += (inner_skull - brain) * 165                 # CSF in the subarachnoid space
    img += brain * 108                                 # white matter baseline

    # cortical ribbon: grey matter is brighter than white matter on T2
    cortex = np.clip(brain - _ellipse_mask(w, h, cx, cy, rx * 0.835, ry * 0.805,
                                           feather=0.12), 0, 1)
    img += cortex * 26

    # sulci: CSF-filled infoldings cutting into the cortex
    yy, xx = np.mgrid[0:h, 0:w]
    ang = np.arctan2((yy - cy) / ry, (xx - cx) / rx)
    rad = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    # Gyral folding is driven by smoothed noise, not by angle: real sulci are
    # irregular, and an angular function produces an obvious radial starburst.
    fold = _grain(w, h, rng, 1.0)
    fold = np.asarray(
        Image.fromarray(np.clip((fold - fold.min()) / (np.ptp(fold) + 1e-9) * 255, 0, 255)
                        .astype(np.uint8)).filter(ImageFilter.GaussianBlur(w * 0.012)),
        dtype=np.float32) / 255.0
    fold = (fold - fold.mean()) / (fold.std() + 1e-9)
    # ridge transform turns the noise field into branching, sulcus-like lines
    sulci = np.clip(1.0 - np.abs(fold) * 1.15, 0, 1) ** 1.4
    depth = np.clip((rad - 0.46) / 0.50, 0, 1) ** 0.7
    img += sulci * depth * brain * 66

    # interhemispheric fissure with the falx inside it
    fissure = _ellipse_mask(w, h, cx, cy, w * 0.009, ry * 0.90, feather=0.55)
    img += fissure * brain * 58

    # lateral ventricles: paired slit-like bodies with frontal horns
    vent = np.zeros((h, w), dtype=np.float32)
    for side in (-1, 1):
        vx = cx + side * w * 0.052
        vent += _ellipse_mask(w, h, vx, cy + h * 0.010, w * 0.026, h * 0.095,
                              rot=side * 0.16, feather=0.22)
        vent += _ellipse_mask(w, h, vx + side * w * 0.020, cy - h * 0.080,
                              w * 0.030, h * 0.044, rot=side * 0.72, feather=0.26)
        vent += _ellipse_mask(w, h, vx + side * w * 0.034, cy + h * 0.082,
                              w * 0.022, h * 0.040, rot=-side * 0.55, feather=0.30)
    vent = np.clip(vent, 0, 1)
    img = img * (1 - vent * 0.90) + vent * 0.90 * 206

    # third ventricle
    third = _ellipse_mask(w, h, cx, cy + h * 0.020, w * 0.009, h * 0.055, feather=0.40)
    img = img * (1 - third * 0.80) + third * 0.80 * 192

    # deep grey nuclei: thalami and basal ganglia
    for side in (-1, 1):
        img += _ellipse_mask(w, h, cx + side * w * 0.042, cy + h * 0.045,
                             w * 0.034, h * 0.040, rot=side * 0.2, feather=0.30) * 14
        img += _ellipse_mask(w, h, cx + side * w * 0.098, cy - h * 0.005,
                             w * 0.030, h * 0.048, rot=side * 0.35, feather=0.30) * 18
        img -= _ellipse_mask(w, h, cx + side * w * 0.072, cy + h * 0.005,
                             w * 0.012, h * 0.040, rot=side * 0.3, feather=0.35) * 10

    img += _grain(w, h, rng, 3.4) * brain
    img *= _vignette(w, h, 0.16)
    return _to_image(img).filter(ImageFilter.GaussianBlur(0.65))


# ------------------------------------------------------------ cardiac ultrasound
def _ultrasound(study: Study) -> Image.Image:
    """B-mode echo. Built from an echogenicity map modulating a speckle field -
    blood pools are anechoic, myocardium is bright, nothing is drawn as a line."""
    w, h = study.width, study.height
    rng = _rng(study.seed)

    apex_x, apex_y = w * 0.5, h * 0.04
    half = math.radians(38)
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = xx - apex_x, yy - apex_y
    r = np.sqrt(dx ** 2 + dy ** 2)
    theta = np.arctan2(dx, np.maximum(dy, 1e-6))
    sector = ((np.abs(theta) <= half) & (r < h * 0.96) & (dy > 0)).astype(np.float32)
    sector = np.asarray(Image.fromarray((sector * 255).astype(np.uint8))
                        .filter(ImageFilter.GaussianBlur(1.4)), dtype=np.float32) / 255.0

    # --- echogenicity map: how strongly each tissue reflects ---
    echo = np.full((h, w), 0.30, dtype=np.float32)      # generic tissue

    # chamber lumens (blood) reflect almost nothing
    lv = _ellipse_mask(w, h, w * 0.432, h * 0.400, w * 0.093, h * 0.158, rot=0.12, feather=0.26)
    rv = _ellipse_mask(w, h, w * 0.593, h * 0.372, w * 0.076, h * 0.126, rot=-0.14, feather=0.28)
    la = _ellipse_mask(w, h, w * 0.447, h * 0.700, w * 0.078, h * 0.082, rot=0.06, feather=0.30)
    ra = _ellipse_mask(w, h, w * 0.581, h * 0.688, w * 0.068, h * 0.074, rot=-0.06, feather=0.30)
    blood = np.clip(lv + rv + la + ra, 0, 1)

    # myocardial walls are the rings around each lumen
    walls = np.clip(
        _annulus(w, h, w * 0.432, h * 0.400, w * 0.093, h * 0.158, w * 0.030, rot=0.12, feather=0.30) * 1.00
        + _annulus(w, h, w * 0.593, h * 0.372, w * 0.076, h * 0.126, w * 0.018, rot=-0.14, feather=0.32) * 0.72
        + _annulus(w, h, w * 0.447, h * 0.700, w * 0.078, h * 0.082, w * 0.014, rot=0.06, feather=0.34) * 0.62
        + _annulus(w, h, w * 0.581, h * 0.688, w * 0.068, h * 0.074, w * 0.013, rot=-0.06, feather=0.34) * 0.58,
        0, 1)

    # interventricular septum between the two ventricles
    septum = _ellipse_mask(w, h, w * 0.513, h * 0.400, w * 0.020, h * 0.150, rot=0.03, feather=0.40)
    # atrioventricular valve plane
    valves = (_ellipse_mask(w, h, w * 0.448, h * 0.566, w * 0.072, h * 0.013, rot=0.10, feather=0.45)
              + _ellipse_mask(w, h, w * 0.590, h * 0.548, w * 0.060, h * 0.011, rot=-0.08, feather=0.45))
    # pericardium as a bright outer envelope
    pericardium = _annulus(w, h, w * 0.508, h * 0.520, w * 0.215, h * 0.300, w * 0.012,
                           rot=0.02, feather=0.30)

    echo += walls * 0.62 + septum * 0.70 + np.clip(valves, 0, 1) * 0.85 + pericardium * 0.55
    echo *= (1 - blood * 0.93)

    # --- speckle: Rayleigh amplitude, correlated to the beam geometry ---
    speckle = rng.rayleigh(scale=1.0, size=(h, w)).astype(np.float32)
    speckle = np.asarray(
        Image.fromarray(np.clip(speckle / (speckle.max() + 1e-9) * 255, 0, 255).astype(np.uint8))
        .filter(ImageFilter.GaussianBlur(0.85)), dtype=np.float32) / 255.0
    # speckle grains elongate along the beam, so smear slightly in depth
    speckle = (speckle + np.roll(speckle, 1, axis=0) + np.roll(speckle, 2, axis=0)) / 3.0

    img = echo * speckle * 430.0

    # time-gain compensation never fully corrects: deep tissue stays darker
    img *= np.clip(1.30 - (r / (h * 0.96)) ** 1.25 * 1.05, 0.10, 1.30)
    # acoustic shadowing behind the brightest reflectors
    shadow = np.clip(1.0 - np.cumsum(walls * 0.0016, axis=0), 0.55, 1.0)
    img *= shadow
    img *= sector
    # faint scan-line structure
    img *= 1.0 + 0.045 * np.sin(theta / max(half, 1e-6) * 150)

    out = _to_image(img)
    d = ImageDraw.Draw(out)
    for i in range(1, 8):
        y = apex_y + (h * 0.94) * i / 8
        d.line([(w - 12, y), (w - 5, y)], fill=160, width=1)
    for lbl, fx, fy in (("LV", 0.432, 0.400), ("RV", 0.593, 0.372),
                        ("LA", 0.447, 0.700), ("RA", 0.581, 0.688)):
        d.text((w * fx - 8, h * fy - 6), lbl, fill=205)
    return out.filter(ImageFilter.GaussianBlur(0.35))


# ------------------------------------------------------------------- CT abdomen
def _ct_abdomen(study: Study) -> Image.Image:
    """Axial CT at roughly the level of the renal hila, in soft-tissue window."""
    w, h = study.width, study.height
    rng = _rng(study.seed)
    img = np.full((h, w), 3.0, dtype=np.float32)

    cx, cy = w * 0.5, h * 0.505
    body = _ellipse_mask(w, h, cx, cy, w * 0.435, h * 0.335, feather=0.030)
    muscle = _ellipse_mask(w, h, cx, cy, w * 0.395, h * 0.296, feather=0.045)

    img += body * 52                      # subcutaneous fat is darker than muscle
    img += muscle * 46                    # peritoneal contents

    # liver: large, homogeneous, patient's right (image left)
    liver = _ellipse_mask(w, h, w * 0.330, h * 0.425, w * 0.195, h * 0.165, rot=0.22, feather=0.09)
    liver *= (1 - _ellipse_mask(w, h, w * 0.46, h * 0.52, w * 0.16, h * 0.15, feather=0.3) * 0.55)
    img += liver * 30
    # portal vessels inside the liver read slightly darker
    img -= _soft(w, h, 2.0, lambda d: [
        d.line([(w * 0.40, h * 0.45), (w * 0.33, h * 0.40)], fill=90, width=4),
        d.line([(w * 0.40, h * 0.45), (w * 0.31, h * 0.47)], fill=80, width=3)]) * 0.14 * (liver > 0.3)

    # spleen, smaller, patient's left
    img += _ellipse_mask(w, h, w * 0.712, h * 0.418, w * 0.088, h * 0.092, rot=-0.35, feather=0.14) * 28

    # stomach: gas in the non-dependent part, fluid dependently
    stomach = _ellipse_mask(w, h, w * 0.560, h * 0.372, w * 0.092, h * 0.078, rot=0.18, feather=0.16)
    img -= stomach * 44
    img += _ellipse_mask(w, h, w * 0.560, h * 0.400, w * 0.084, h * 0.034, feather=0.30) * 40

    # kidneys with lower-density collecting systems
    for side in (-1, 1):
        kx = cx + side * w * 0.178
        img += _ellipse_mask(w, h, kx, h * 0.570, w * 0.062, h * 0.052, rot=side * 0.3, feather=0.14) * 34
        img -= _ellipse_mask(w, h, kx + side * w * 0.012, h * 0.570,
                             w * 0.022, h * 0.020, rot=side * 0.3, feather=0.3) * 18

    # small bowel: a contiguous central cluster of loops, each a wall ring round gas
    for _ in range(9):
        ang = rng.uniform(0, 2 * math.pi)
        rad = rng.uniform(0, 1) ** 0.6
        bx = cx + math.cos(ang) * rad * w * 0.155
        by = h * 0.545 + math.sin(ang) * rad * h * 0.085
        rr = rng.uniform(0.028, 0.045)
        img += _annulus(w, h, bx, by, w * rr, h * rr * 0.95, w * rr * 0.30, feather=0.34) * 16
        img -= _ellipse_mask(w, h, bx, by, w * rr * 0.64, h * rr * 0.60, feather=0.42) * 14

    # vertebral body: cortical rim bright, trabecular centre less so, canal dark
    img += _ellipse_mask(w, h, cx, h * 0.690, w * 0.072, h * 0.058, feather=0.05) * 150
    img -= _ellipse_mask(w, h, cx, h * 0.690, w * 0.052, h * 0.040, feather=0.15) * 62
    img -= _ellipse_mask(w, h, cx, h * 0.735, w * 0.028, h * 0.024, feather=0.2) * 70
    # transverse and spinous processes
    for side in (-1, 1):
        img += _ellipse_mask(w, h, cx + side * w * 0.098, h * 0.690,
                             w * 0.034, h * 0.016, rot=side * 0.2, feather=0.15) * 120
    img += _ellipse_mask(w, h, cx, h * 0.778, w * 0.016, h * 0.040, feather=0.15) * 115

    # aorta and inferior vena cava
    img += _ellipse_mask(w, h, cx - w * 0.030, h * 0.620, w * 0.026, h * 0.024, feather=0.16) * 42
    img += _ellipse_mask(w, h, cx + w * 0.036, h * 0.616, w * 0.030, h * 0.022, feather=0.20) * 34

    # psoas muscles flanking the spine
    for side in (-1, 1):
        img += _ellipse_mask(w, h, cx + side * w * 0.072, h * 0.655,
                             w * 0.040, h * 0.038, rot=side * 0.25, feather=0.18) * 22

    # ribs: short cortical segments lying along the body wall, tangent to it
    ribs_a, ribs_b = w * 0.408, h * 0.312
    for i in range(13):
        t = math.pi * (-0.46 + i / 12 * 0.92)          # lateral and posterior wall only
        for side in (-1, 1):
            px = cx + side * ribs_a * math.cos(t)
            py = cy + ribs_b * math.sin(t)
            tangent = math.atan2(ribs_b * math.cos(t), -side * ribs_a * math.sin(t))
            img += _ellipse_mask(w, h, px, py, w * 0.024, h * 0.009,
                                 rot=-tangent, feather=0.30) * 95 * (0.75 + 0.25 * (i % 2))

    img += _grain(w, h, rng, 3.0) * body
    img *= _vignette(w, h, 0.14)
    return _to_image(img).filter(ImageFilter.GaussianBlur(0.45))


# ------------------------------------------------------------------------ ECG
def _ecg(study: Study) -> Image.Image:
    w, h = study.width, max(study.height, 300)
    rng = _rng(study.seed)
    img = Image.new("RGB", (w, h), (255, 252, 250))
    d = ImageDraw.Draw(img)

    small = max(w // 60, 5)
    for x in range(0, w, small):
        d.line([(x, 0), (x, h)], fill=(252, 216, 210), width=1)
    for y in range(0, h, small):
        d.line([(0, y), (w, y)], fill=(252, 216, 210), width=1)
    for x in range(0, w, small * 5):
        d.line([(x, 0), (x, h)], fill=(243, 160, 150), width=1)
    for y in range(0, h, small * 5):
        d.line([(0, y), (w, y)], fill=(243, 160, 150), width=1)

    bpm = study.measurements.get("heart_rate")
    rate = float(bpm.split()[0]) if bpm and bpm.split()[0].replace(".", "").isdigit() else 72.0
    leads = ["II", "V1", "V5"]
    rows = len(leads)
    beat_px = max(w * 60.0 / (rate * 5.0), 34)

    for li, lead in enumerate(leads):
        baseline = h * (0.22 + li * 0.30)
        amp = {"II": 1.0, "V1": 0.62, "V5": 0.88}[lead]
        pts: list[tuple[float, float]] = []
        x = 6.0
        while x < w - 6:
            jitter = rng.normal(0, beat_px * 0.012)
            for frac, mv in (
                (0.00, 0.0), (0.10, 0.0), (0.16, 0.14), (0.22, 0.0),   # P wave
                (0.28, 0.0), (0.31, -0.08), (0.34, 1.0),               # Q, R
                (0.37, -0.22), (0.40, 0.0),                            # S
                (0.52, 0.0), (0.62, 0.26), (0.72, 0.0), (1.0, 0.0),    # T wave
            ):
                px = x + frac * beat_px + jitter
                sign = -1 if lead == "V1" and mv > 0.5 else 1
                py = baseline - mv * amp * sign * h * 0.115
                py += rng.normal(0, 0.5)
                if px < w - 4:
                    pts.append((px, py))
            x += beat_px
        if len(pts) > 1:
            d.line(pts, fill=(18, 22, 30), width=2)
        d.text((8, baseline - h * 0.165), lead, fill=(60, 68, 84))

    d.line([(6, h - 16), (6, h - 42)], fill=(18, 22, 30), width=2)
    d.line([(6, h - 42), (small * 5 + 6, h - 42)], fill=(18, 22, 30), width=2)
    d.line([(small * 5 + 6, h - 42), (small * 5 + 6, h - 16)], fill=(18, 22, 30), width=2)
    d.text((small * 5 + 12, h - 40), "1mV / 0.2s", fill=(90, 98, 112))
    return img


_GENERATORS = {
    "xray_chest": _chest_xray,
    "mri_brain": _brain_mri,
    "ultrasound_cardiac": _ultrasound,
    "ct_abdomen": _ct_abdomen,
    "ecg": _ecg,
}


def _watermark(img: Image.Image, study: Study) -> Image.Image:
    """Burn SIMULATED into the pixels. This is not a removable caption."""
    rgb = img.convert("RGB")
    d = ImageDraw.Draw(rgb)
    w, h = rgb.size
    try:
        font = ImageFont.load_default(size=max(11, w // 34))
        small = ImageFont.load_default(size=max(9, w // 46))
    except Exception:
        font = small = ImageFont.load_default()

    dark = study.modality != "ecg"
    fg = (255, 255, 255) if dark else (30, 36, 48)
    dim = (190, 198, 210) if dark else (110, 118, 132)

    d.text((10, 8), study.modality_label, fill=fg, font=small)
    d.text((10, h - 22), f"SEED {study.seed}", fill=dim, font=small)

    tag = "SIMULATED — NOT A REAL PATIENT STUDY"
    box = d.textbbox((0, 0), tag, font=small)
    tw = box[2] - box[0]
    d.text(((w - tw) / 2, h - 22), tag, fill=(239, 68, 68), font=small)

    # diagonal ghost watermark across the field
    ghost = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(ghost)
    gbox = gd.textbbox((0, 0), "SIMULATED", font=font)
    gw, gh = gbox[2] - gbox[0], gbox[3] - gbox[1]
    for i in range(-1, 3):
        gd.text((w * 0.14, h * 0.30 + i * (gh + h * 0.22)), "SIMULATED",
                fill=(255, 255, 255, 46) if dark else (0, 0, 0, 34), font=font)
    ghost = ghost.rotate(28, resample=Image.BICUBIC, center=(w / 2, h / 2))
    rgb = Image.alpha_composite(rgb.convert("RGBA"), ghost).convert("RGB")
    return rgb


def generate(study: Study) -> Image.Image:
    gen = _GENERATORS.get(study.modality)
    if gen is None:
        raise ValueError(f"unknown modality: {study.modality}")
    return _watermark(gen(study), study)


def to_png_bytes(study: Study) -> bytes:
    buf = io.BytesIO()
    generate(study).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_data_uri(study: Study) -> str:
    return "data:image/png;base64," + base64.b64encode(to_png_bytes(study)).decode()


def study_for(modality: str, key: str, label: str | None = None,
              findings: list[str] | None = None,
              measurements: dict[str, str] | None = None,
              size: tuple[int, int] = (420, 420)) -> Study:
    """Deterministic study from a stable key, so the same record always renders
    the same image across reruns."""
    seed = int(hashlib.sha1(f"{modality}|{key}".encode()).hexdigest()[:8], 16) % 10_000_000
    return Study(
        study_id=f"img_{hashlib.sha1(f'{modality}|{key}'.encode()).hexdigest()[:10]}",
        modality=modality, label=label or MODALITIES.get(modality, modality), seed=seed,
        width=size[0], height=size[1],
        findings=findings or [], measurements=measurements or {},
    )
