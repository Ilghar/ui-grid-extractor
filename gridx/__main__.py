import argparse, json, sys
from . import core, fixtures

def main(argv=None):
    ap = argparse.ArgumentParser(prog="gridx", description="Measured UI grid & token extractor (ilghar.studio)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyse", help="analyse a measured-coordinates JSON fixture")
    a.add_argument("fixture"); a.add_argument("--from-svg", action="store_true", help="input is an SVG with rect/text boxes"); a.add_argument("--svg"); a.add_argument("--theme", choices=["light", "dark"], default="light"); a.add_argument("--css")
    sub.add_parser("validate").add_argument("fixture")
    g = sub.add_parser("fixtures", help="write deterministic synthetic fixtures"); g.add_argument("outdir")
    sub.add_parser("verify", help="check analyser against known synthetic geometry")
    t = sub.add_parser("tokens", help="check colours, fonts and 4px spacing against DESIGN_TOKENS.json")
    t.add_argument("fixture"); t.add_argument("--tokens", default="fixtures/ilghar_studio_DESIGN_TOKENS.json")
    ns = ap.parse_args(argv)
    if ns.cmd == "tokens":
        from .tokens import TokenCheck
        with open(ns.fixture, encoding="utf-8") as fh:
            res = TokenCheck.check(json.load(fh), TokenCheck.load_tokens(ns.tokens))
        sys.stdout.write(core.dumps(res)); return 0 if res["ok"] else 1
    if ns.cmd == "fixtures":
        import os; os.makedirs(ns.outdir, exist_ok=True)
        for k, f in fixtures.ALL.items():
            open(os.path.join(ns.outdir, k + ".json"), "w").write(core.dumps(f()))
        return 0
    if ns.cmd == "verify":
        from .verify import run; res = run(); sys.stdout.write(core.dumps(res)); return 0 if res["passed"] == res["total"] else 1
    skipped = None
    try:
        with open(ns.fixture, encoding="utf-8") as fh:
            raw = fh.read()
        if getattr(ns, "from_svg", False):
            from .svgsrc import parse_svg
            doc, skipped = parse_svg(raw)
        else:
            doc = json.loads(raw, parse_constant=lambda c: float(c))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        sys.stdout.write(core.dumps({"valid": False, "errors": ["cannot read input: %s" % e]})); return 2
    try:
        core.validate(doc)
    except core.FixtureError as e:
        sys.stdout.write(core.dumps({"valid": False, "errors": e.args[0]})); return 2
    if ns.cmd == "validate":
        sys.stdout.write(core.dumps({"valid": True})); return 0
    r = core.analyse(doc)
    if skipped is not None:
        r["svg_skipped"] = skipped
    try:
        if ns.svg: open(ns.svg, "w", encoding="utf-8").write(core.svg_overlay(doc, r, ns.theme))
        if ns.css: open(ns.css, "w", encoding="utf-8").write(core.css_tokens(r))
    except OSError as e:
        sys.stdout.write(core.dumps({"valid": True, "errors": ["cannot write output: %s" % e]})); return 2
    sys.stdout.write(core.dumps(r)); return 0

if __name__ == "__main__":
    sys.exit(main())
