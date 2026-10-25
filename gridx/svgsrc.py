"""SVG source: read <rect> and <text> boxes from a self-authored SVG (stdlib xml).

Only explicit geometry is used. Transforms other than translate(), and text
without explicit data-w/data-h, are reported as skipped rather than guessed.
"""
import re
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
_NUM = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|pt|mm)?\s*$")
_TR = re.compile(r"^\s*translate\(\s*(-?[\d.]+)(?:[\s,]+(-?[\d.]+))?\s*\)\s*$")


def _num(v):
    if v is None:
        return None, None
    m = _NUM.match(v)
    if not m:
        raise ValueError("unsupported length %r" % v)
    return float(m.group(1)), m.group(2)


def parse_svg(text, tolerance=0.5):
    root = ET.fromstring(text)
    if root.tag not in (NS + "svg", "svg"):
        raise ValueError("root element is not <svg>")
    w, wu = _num(root.get("width"))
    h, hu = _num(root.get("height"))
    if (w is None or h is None) and root.get("viewBox"):
        _, _, w, h = [float(x) for x in root.get("viewBox").replace(",", " ").split()]
    unit = wu or hu or "px"
    elements, skipped = [], []

    def walk(node, ox, oy, ok):
        tr = node.get("transform")
        if tr:
            m = _TR.match(tr)
            if m:
                ox += float(m.group(1)); oy += float(m.group(2) or 0)
            else:
                ok = False
        tag = node.tag.replace(NS, "")
        eid = node.get("id")
        if tag in ("rect", "text") and node is not root:
            if not ok:
                skipped.append({"id": eid, "reason": "non-translate transform"})
            elif not eid:
                skipped.append({"id": None, "reason": "%s without id" % tag})
            elif tag == "rect":
                g = {k: _num(node.get(k))[0] for k in ("x", "y", "width", "height")}
                if g["width"] is None or g["height"] is None:
                    skipped.append({"id": eid, "reason": "rect without width/height"})
                else:
                    elements.append({"id": eid, "x": ox + (g["x"] or 0), "y": oy + (g["y"] or 0),
                                     "w": g["width"], "h": g["height"], "role": node.get("data-role", "rect")})
            else:
                bw, bh = _num(node.get("data-w"))[0], _num(node.get("data-h"))[0]
                fs = _num(node.get("font-size"))[0]
                if bw is None or bh is None:
                    skipped.append({"id": eid, "reason": "text box size not declared (data-w/data-h); not inferred"})
                else:
                    x = _num(node.get("x"))[0] or 0
                    y = _num(node.get("y"))[0] or 0  # y is the box top via data-top convention
                    top = _num(node.get("data-top"))[0]
                    e = {"id": eid, "x": ox + x, "y": oy + (top if top is not None else y), "w": bw, "h": bh,
                         "role": node.get("data-role", "text")}
                    if fs:
                        e["font_size"] = fs
                    elements.append(e)
        for c in node:
            walk(c, ox, oy, ok)

    walk(root, 0.0, 0.0, True)
    doc = {"schema_version": 1, "name": root.get("id", "svg-source"), "unit": unit, "zoom": 1,
           "tolerance": tolerance, "frame": {"width": w, "height": h}, "elements": elements}
    return doc, skipped
