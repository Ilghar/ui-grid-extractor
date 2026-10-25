"""Deterministic self-authored synthetic fixtures with known ground truth."""

def card_8px():
    # 3-column, 24px margin, 112px pitch, 8px rhythm, 1.25 type scale (scaled from 16).
    els = []
    for c in range(3):
        x = 24 + c * 112
        els.append({"id": "card%d" % c, "x": x, "y": 96, "w": 96, "h": 128, "role": "card"})
    els.append({"id": "title", "x": 24, "y": 32, "w": 320, "h": 40, "font_size": 25, "role": "heading"})
    els.append({"id": "lead", "x": 24, "y": 248, "w": 320, "h": 24, "font_size": 20, "role": "text"})
    els.append({"id": "body", "x": 24, "y": 296, "w": 320, "h": 48, "font_size": 16, "role": "text"})
    els.append({"id": "meta", "x": 24, "y": 368, "w": 200, "h": 16, "font_size": 12.8, "role": "caption"})
    return {"schema_version": 1, "name": "synthetic/card-8px", "unit": "px", "zoom": 1, "tolerance": 0.5,
            "frame": {"width": 376, "height": 400}, "elements": els,
            "truth": {"base_px": 8, "columns": 3, "pitch_px": 112, "margin_px": 24}}

def card_8px_zoom2_pt():
    """Same layout measured in pt at 200% zoom: values = px * 0.75 * 2."""
    d = card_8px()
    f = 0.75 * 2
    for e in d["elements"]:
        for k in ("x", "y", "w", "h", "font_size"):
            if k in e:
                e[k] = round(e[k] * f, 6)
    d["frame"] = {"width": 376 * f, "height": 400 * f}
    d.update(name="synthetic/card-8px@pt-zoom2", unit="pt", zoom=2)
    return d

def misaligned():
    d = card_8px()
    d["name"] = "synthetic/card-misaligned"
    d["elements"][1]["x"] += 3  # card1 nudged 3px off the column guide
    d["truth"] = {"base_px": None, "misaligned": ["card1"]}
    return d

def rhythm_5px():
    els = [{"id": "a", "x": 15, "y": 15, "w": 35, "h": 25}, {"id": "b", "x": 15, "y": 55, "w": 65, "h": 10},
           {"id": "c", "x": 15, "y": 85, "w": 45, "h": 35}]
    return {"schema_version": 1, "name": "synthetic/5px-rhythm", "unit": "px", "zoom": 1, "tolerance": 0.5,
            "frame": {"width": 120, "height": 140}, "elements": els, "truth": {"base_px": 5}}

ALL = {"card-8px": card_8px, "card-8px-pt-zoom2": card_8px_zoom2_pt, "card-misaligned": misaligned,
       "rhythm-5px": rhythm_5px}
