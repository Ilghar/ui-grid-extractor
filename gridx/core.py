"""Core: unit normalisation, grid hypotheses, residuals, tokens, SVG overlay.

Inputs are explicit measured coordinates (never pixels guessed from images).
No default 4/8pt grid: a base unit is only reported when the evidence supports it.
"""
import json, math
from xml.sax.saxutils import escape

UNITS_TO_PX = {"px": 1.0, "pt": 96.0 / 72.0, "mm": 96.0 / 25.4}
SCHEMA_VERSION = 1
CANDIDATE_BASES = (2, 3, 4, 5, 6, 8, 10, 12, 16)


class FixtureError(ValueError):
    pass


MIN_ELEMENTS = 3   # minimum elements before a base unit is claimed
MIN_GUIDES = 3     # minimum distinct column guides before columns are claimed
MAX_ZOOM = 64.0
MIN_ZOOM = 1.0 / 64


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate(doc):
    errs = []
    if not isinstance(doc, dict):
        raise FixtureError(["fixture must be an object"])
    sv = doc.get("schema_version")
    if isinstance(sv, bool) or sv != SCHEMA_VERSION:
        errs.append("schema_version must be the integer 1")
    unit = doc.get("unit")
    if not isinstance(unit, str) or unit not in UNITS_TO_PX:
        errs.append("unit must be one of px, pt, mm (got %r)" % (unit,))
    zoom = doc.get("zoom", 1.0)
    if not _isnum(zoom) or not (MIN_ZOOM <= zoom <= MAX_ZOOM):
        errs.append("zoom must be a finite number in [1/64, 64]")
    fr = doc.get("frame")
    if not (isinstance(fr, dict) and all(_isnum(fr.get(k)) and fr.get(k) > 0 for k in ("width", "height"))):
        errs.append("frame.width and frame.height must be positive finite numbers")
    els = doc.get("elements")
    if not isinstance(els, list) or not els:
        errs.append("elements must be a non-empty list")
        els = []
    ids = set()
    for i, e in enumerate(els):
        if not isinstance(e, dict):
            errs.append("elements[%d] must be an object" % i); continue
        if not isinstance(e.get("id"), str) or not e["id"]:
            errs.append("elements[%d].id must be a non-empty string" % i)
        elif e["id"] in ids:
            errs.append("duplicate element id %r" % e["id"])
        else:
            ids.add(e["id"])
        for k in ("x", "y", "w", "h"):
            v = e.get(k)
            if not _isnum(v):
                errs.append("elements[%d].%s must be a finite number" % (i, k))
            elif v < 0 or (k in ("w", "h") and v == 0):
                errs.append("elements[%d].%s must be %s" % (i, k, "> 0" if k in ("w", "h") else ">= 0"))
        if "font_size" in e and not (_isnum(e["font_size"]) and e["font_size"] > 0):
            errs.append("elements[%d].font_size must be a positive finite number" % i)
    tol = doc.get("tolerance", 0.5)
    if not _isnum(tol) or tol < 0:
        errs.append("tolerance must be a finite number >= 0")
    elif isinstance(unit, str) and unit in UNITS_TO_PX and _isnum(zoom) and zoom > 0:
        tol_px = tol * UNITS_TO_PX[unit] / zoom
        if tol_px >= min(CANDIDATE_BASES) / 2:
            errs.append("tolerance %.4gpx must be < %gpx (half the smallest candidate base)" % (tol_px, min(CANDIDATE_BASES) / 2))
    if not errs:
        errs = Bounds.after_normalise(doc)
    if errs:
        raise FixtureError(errs)
    return doc


class Bounds:
    """Checks that only hold after unit/zoom conversion and 4-decimal rounding."""
    MIN_PX = 1e-4  # smallest positive value that survives round(v, 4)
    MAX_BASELINES = 4096  # overlay draws no baseline lines beyond this many (frame too tall to render)

    @staticmethod
    def after_normalise(doc):
        f = UNITS_TO_PX[doc["unit"]] / float(doc.get("zoom", 1.0))
        errs = []
        for i, e in enumerate(doc["elements"]):
            for k in ("x", "y", "w", "h", "font_size"):
                if k not in e:
                    continue
                v = e[k] * f
                if not math.isfinite(v):
                    errs.append("elements[%d].%s overflows after unit/zoom conversion" % (i, k))
                elif e[k] > 0 and round(v, 4) < Bounds.MIN_PX:
                    errs.append("elements[%d].%s rounds to 0px after conversion (must be >= %gpx)" % (i, k, Bounds.MIN_PX))
        if not all(math.isfinite(doc["frame"][k] * f) for k in ("width", "height")):
            errs.append("frame overflows after unit/zoom conversion")
        return errs


def normalise(doc):
    """Convert to CSS px at zoom 1. Measured values are divided by zoom."""
    f = UNITS_TO_PX[doc["unit"]] / float(doc.get("zoom", 1.0))
    r = lambda v: round(v * f, 4)
    out = []
    for e in doc["elements"]:
        n = {"id": e["id"], "x": r(e["x"]), "y": r(e["y"]), "w": r(e["w"]), "h": r(e["h"])}
        if "font_size" in e:
            n["font_size"] = r(e["font_size"])
        if "role" in e:
            n["role"] = e["role"]
        out.append(n)
    return {"factor": f, "frame": {"width": r(doc["frame"]["width"]), "height": r(doc["frame"]["height"])},
            "elements": out, "tolerance": float(doc.get("tolerance", 0.5)) * f}


def _residual(v, base):
    m = v % base
    return min(m, base - m)


def baseline_hypotheses(values, tol, n_elements=None):
    """Score each candidate base unit by fraction of values within tol of a multiple."""
    vals = [v for v in values if v != 0]  # zero is a multiple of every base: carries no evidence
    hyps = []
    for b in CANDIDATE_BASES:
        res = [_residual(v, b) for v in vals]
        fit = sum(1 for x in res if x <= tol) / len(vals) if vals else 0.0
        hyps.append({"base_px": b, "fit": round(fit, 4), "max_residual": round(max(res), 4) if res else None,
                     "mean_residual": round(sum(res) / len(res), 4) if res else None})
    hyps.sort(key=lambda h: (-h["fit"], -h["base_px"]))
    full = [h for h in hyps if h["fit"] == 1.0]
    if n_elements is not None and n_elements < MIN_ELEMENTS:
        return {"verdict": "insufficient", "base_px": None, "competing": [], "candidates": hyps, "n_values": len(vals),
                "note": "fewer than %d elements; no base unit is claimed" % MIN_ELEMENTS}
    if full:
        best = max(full, key=lambda h: h["base_px"])
        # Ambiguous if another exact base is not a divisor of the best (genuinely competing).
        rivals = [h["base_px"] for h in full if best["base_px"] % h["base_px"] != 0]
        verdict = "ambiguous" if rivals else "supported"
        return {"verdict": verdict, "base_px": best["base_px"], "competing": rivals, "candidates": hyps,
                "n_values": len(vals)}
    return {"verdict": "unsupported", "base_px": None, "competing": [], "candidates": hyps, "n_values": len(vals),
            "note": "no candidate base fits every measured value within tolerance; no grid is claimed"}


def _cluster(vals, tol):
    groups = []
    for v in sorted(vals):
        if groups and v - groups[-1][0] <= tol:  # anchored to cluster start: no chaining
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


def columns(norm):
    """Infer column guides from left edges; derive gutter/column width if regular."""
    tol = max(norm["tolerance"], 1e-9)
    lefts = _cluster([e["x"] for e in norm["elements"]], tol)
    guides = [round(sum(g) / len(g), 4) for g in lefts]
    steps = [round(b - a, 4) for a, b in zip(guides, guides[1:])]
    regular = len(guides) >= MIN_GUIDES and (max(steps) - min(steps) <= tol)
    margin = guides[0] if guides else None
    return {"guides_px": guides, "steps_px": steps, "regular": regular,
            "evidence": "sufficient" if len(guides) >= MIN_GUIDES else "insufficient",
            "pitch_px": round(sum(steps) / len(steps), 4) if regular else None,
            "margin_left_px": margin,
            "misaligned": [e["id"] for e in norm["elements"]
                           if min(abs(e["x"] - g) for g in guides) > tol]}


def spacing(norm):
    """Vertical gaps between consecutive elements sorted by y (stacked flow)."""
    els = sorted(norm["elements"], key=lambda e: (e["y"], e["x"]))
    gaps = []
    for a, b in zip(els, els[1:]):
        g = round(b["y"] - (a["y"] + a["h"]), 4)
        if g > 0:
            gaps.append(g)
    return sorted(set(gaps))


def type_scale(norm):
    sizes = sorted({e["font_size"] for e in norm["elements"] if "font_size" in e})
    ratios = [round(b / a, 4) for a, b in zip(sizes, sizes[1:])]
    consistent = len(ratios) >= 2 and max(ratios) - min(ratios) <= 0.02
    return {"sizes_px": sizes, "ratios": ratios,
            "modular_ratio": round(sum(ratios) / len(ratios), 4) if consistent else None,
            "verdict": "modular" if consistent else ("insufficient" if len(ratios) < 2 else "non-modular")}


def analyse(doc):
    validate(doc)
    n = normalise(doc)
    vals = []
    for e in n["elements"]:
        vals += [e["x"], e["y"], e["w"], e["h"]]
    gaps = spacing(n)
    base = baseline_hypotheses(vals + gaps, n["tolerance"], len(n["elements"]))
    cols = columns(n)
    ref = base["base_px"] or base["candidates"][0]["base_px"]
    off = [e["id"] for e in n["elements"]
           if any(_residual(e[k], ref) > n["tolerance"] for k in ("x", "y", "w", "h"))]
    cols["misaligned"] = sorted(set(cols["misaligned"]) | set(off))
    cols["reference_base_px"] = ref
    ts = type_scale(n)
    fields = {"base_unit": base["verdict"] == "supported", "columns": cols["regular"],
              "spacing": bool(gaps), "type_scale": ts["verdict"] == "modular"}
    report = {
        "schema_version": SCHEMA_VERSION, "source": doc.get("name", "unnamed"),
        "input_unit": doc["unit"], "zoom": doc.get("zoom", 1.0), "px_factor": round(n["factor"], 6),
        "frame_px": n["frame"], "tolerance_px": round(n["tolerance"], 4),
        "base_unit": base, "columns": cols, "spacing_px": gaps, "type_scale": ts,
        "exact": base["verdict"] == "supported" and not cols["misaligned"],
        "measured_support": round(sum(fields.values()) / len(fields), 4), "supported_fields": fields,
    }
    report["tokens"] = tokens(report)
    return report


def tokens(r):
    t = {}
    if r["base_unit"]["verdict"] == "supported":
        t["space.base"] = "%gpx" % r["base_unit"]["base_px"]
    for i, g in enumerate(r["spacing_px"]):
        t["space.%d" % (i + 1)] = "%gpx" % g
    if r["columns"]["regular"]:
        t["grid.pitch"] = "%gpx" % r["columns"]["pitch_px"]
        t["grid.margin"] = "%gpx" % r["columns"]["margin_left_px"]
        t["grid.columns"] = len(r["columns"]["guides_px"])
    for i, s in enumerate(r["type_scale"]["sizes_px"]):
        t["font.size.%d" % i] = "%gpx" % s
    if r["type_scale"]["modular_ratio"]:
        t["font.ratio"] = r["type_scale"]["modular_ratio"]
    return t


def css_tokens(r):
    lines = [":root {"]
    for k, v in r["tokens"].items():
        lines.append("  --%s: %s;" % (k.replace(".", "-"), v))
    lines.append("}")
    return "\n".join(lines) + "\n"


THEMES = {  # from Ilghar/ilghar-studio src/styles.css (:root and .dark)
    "light": {"canvas": "#f3f1f6", "ink": "#4a3a5c", "muted": "#7a688c", "subtle": "#a394ae", "accent": "#c97a98"},
    "dark": {"canvas": "#4a434c", "ink": "#f4eef3", "muted": "#cbbdce", "subtle": "#cbbdce", "accent": "#e8a8bc"},
}


def svg_overlay(doc, r, theme="light"):
    if theme not in THEMES:
        raise ValueError("theme must be light or dark")
    T = THEMES[theme]
    n = normalise(doc)
    W, H = n["frame"]["width"], n["frame"]["height"]
    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" width="%g" height="%g">' % (W, H, W, H),
         '<rect width="100%%" height="100%%" fill="%s"/>' % T["canvas"]]
    b = r["base_unit"]["base_px"] if r["base_unit"]["verdict"] == "supported" else None
    if b and H / b <= Bounds.MAX_BASELINES:
        y = 0
        while y <= H:
            p.append('<line x1="0" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="0.25" opacity="0.5"/>' % (y, W, y, T["subtle"]))
            y += b
    for g in r["columns"]["guides_px"]:
        p.append('<line x1="%g" y1="0" x2="%g" y2="%g" stroke="%s" stroke-width="1"/>' % (g, g, H, T["accent"]))
    mis = set(r["columns"]["misaligned"])
    for e in n["elements"]:
        bad = e["id"] in mis
        # flags never rely on hue alone: dashed ink stroke + accent tint + text label
        p.append('<rect x="%g" y="%g" width="%g" height="%g" fill="%s" fill-opacity="%s" stroke="%s" stroke-width="1.5"%s/>' % (
            e["x"], e["y"], e["w"], e["h"], T["accent"], "0.35" if bad else "0", T["ink"], ' stroke-dasharray="4 2"' if bad else ""))
        p.append('<text x="%g" y="%g" font-family="Jost, sans-serif" font-size="9" fill="%s">%s</text>' % (
            e["x"] + 3, e["y"] + 11, T["ink"], "\u2068" + escape(e["id"]) + "\u2069" + (" \u2715 misaligned" if bad else "")))
    p.append("</svg>")
    p[0] = p[0].replace("<svg ", '<svg data-theme="%s" ' % theme, 1)
    return "\n".join(p) + "\n"


def dumps(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def contrast(a, b):
    """WCAG 2.x contrast ratio between two #rrggbb colours."""
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)
