import os, subprocess, sys, json, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gridx import core, fixtures
from gridx.svgsrc import parse_svg

SVG = os.path.join(ROOT, "fixtures", "card-8px.source.svg")

class SvgSource(unittest.TestCase):
    def test_matches_json_fixture_tokens(self):
        doc, skipped = parse_svg(open(SVG).read())
        self.assertEqual(core.analyse(doc)["tokens"], core.analyse(fixtures.card_8px())["tokens"])
    def test_skips_not_guesses(self):
        _, skipped = parse_svg(open(SVG).read())
        self.assertEqual(sorted(s["id"] for s in skipped), ["free", "rot"])
    def test_units_from_root(self):
        doc, _ = parse_svg('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm"><rect id="a" x="0" y="0" width="10" height="5"/></svg>')
        self.assertEqual(doc["unit"], "mm")
    def test_rejects_non_svg_and_bad_length(self):
        with self.assertRaises(ValueError): parse_svg("<html/>")
        with self.assertRaises(ValueError): parse_svg('<svg xmlns="http://www.w3.org/2000/svg" width="10em" height="5"/>')
    def test_cli_from_svg(self):
        p = subprocess.run([sys.executable, "-m", "gridx", "analyse", "--from-svg", SVG], cwd=ROOT, capture_output=True, text=True, check=True)
        r = json.loads(p.stdout)
        self.assertEqual(r["tokens"]["space.base"], "8px"); self.assertEqual(len(r["svg_skipped"]), 2)

if __name__ == "__main__":
    unittest.main()
