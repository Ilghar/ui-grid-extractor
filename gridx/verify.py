from . import core, fixtures

def run():
    checks = []
    def chk(name, ok): checks.append({"check": name, "ok": bool(ok)})
    r = core.analyse(fixtures.card_8px())
    chk("8px base recovered", r["base_unit"]["verdict"] == "supported" and r["base_unit"]["base_px"] == 8)
    chk("3 columns, 112px pitch, 24px margin", r["columns"]["regular"] and r["columns"]["pitch_px"] == 112 and r["columns"]["margin_left_px"] == 24 and len(r["columns"]["guides_px"]) == 3)
    chk("type scale 1.25", r["type_scale"]["modular_ratio"] == 1.25)
    chk("exact claim on clean fixture", r["exact"])
    z = core.analyse(fixtures.card_8px_zoom2_pt())
    chk("pt@200% normalises to same px tokens", z["tokens"] == r["tokens"])
    m = core.analyse(fixtures.misaligned())
    chk("misaligned guide fails exactness", not m["exact"] and "card1" in m["columns"]["misaligned"])
    a = core.analyse(fixtures.rhythm_5px())
    chk("5px evidence does not become 4/8pt", a["base_unit"]["base_px"] not in (4, 8))
    return {"total": len(checks), "passed": sum(c["ok"] for c in checks), "checks": checks}
