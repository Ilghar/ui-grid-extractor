import argparse, json, sys
from . import core, fixtures

def main(argv=None):
    ap = argparse.ArgumentParser(prog="gridx", description="Measured UI grid & token extractor (ilghar.studio)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyse", help="analyse a measured-coordinates JSON fixture")
    a.add_argument("fixture"); a.add_argument("--svg"); a.add_argument("--css")
    sub.add_parser("validate").add_argument("fixture")
    g = sub.add_parser("fixtures", help="write deterministic synthetic fixtures"); g.add_argument("outdir")
    sub.add_parser("verify", help="check analyser against known synthetic geometry")
    ns = ap.parse_args(argv)
    if ns.cmd == "fixtures":
        import os; os.makedirs(ns.outdir, exist_ok=True)
        for k, f in fixtures.ALL.items():
            open(os.path.join(ns.outdir, k + ".json"), "w").write(core.dumps(f()))
        return 0
    if ns.cmd == "verify":
        from .verify import run; res = run(); sys.stdout.write(core.dumps(res)); return 0 if res["passed"] == res["total"] else 1
    doc = json.load(open(ns.fixture, encoding="utf-8"))
    try:
        core.validate(doc)
    except core.FixtureError as e:
        sys.stdout.write(core.dumps({"valid": False, "errors": e.args[0]})); return 2
    if ns.cmd == "validate":
        sys.stdout.write(core.dumps({"valid": True})); return 0
    r = core.analyse(doc)
    if ns.svg: open(ns.svg, "w").write(core.svg_overlay(doc, r))
    if ns.css: open(ns.css, "w").write(core.css_tokens(r))
    sys.stdout.write(core.dumps(r)); return 0

if __name__ == "__main__":
    sys.exit(main())
