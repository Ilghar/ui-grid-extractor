import json, os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gridx import core, fixtures, verify

class T(unittest.TestCase):
    def test_verify_all(self):
        r = verify.run(); self.assertEqual(r["passed"], r["total"], r)
    def test_no_default_grid(self):
        d = {"schema_version": 1, "unit": "px", "frame": {"width": 100, "height": 100}, "tolerance": 0.2,
             "elements": [{"id": "a", "x": 7.3, "y": 11.1, "w": 33.7, "h": 9.9}]}
        r = core.analyse(d)
        self.assertEqual(r["base_unit"]["verdict"], "unsupported"); self.assertNotIn("space.base", r["tokens"])
    def test_units(self):
        self.assertAlmostEqual(core.UNITS_TO_PX["mm"] * 25.4, 96)
        self.assertAlmostEqual(core.UNITS_TO_PX["pt"] * 72, 96)
    def test_mm_fixture(self):
        d = fixtures.card_8px(); f = 25.4 / 96
        for e in d["elements"]:
            for k in ("x", "y", "w", "h", "font_size"):
                if k in e: e[k] *= f
        d["frame"] = {"width": 376 * f, "height": 400 * f}; d["unit"] = "mm"
        self.assertEqual(core.analyse(d)["base_unit"]["base_px"], 8)
    def test_ambiguous_preserved(self):
        r = core.analyse(fixtures.rhythm_5px())
        self.assertEqual(r["base_unit"]["base_px"], 5)
        d = {"schema_version": 1, "unit": "px", "frame": {"width": 100, "height": 100},
             "elements": [{"id": "a", "x": 20, "y": 40, "w": 60, "h": 80}, {"id": "b", "x": 100, "y": 140, "w": 40, "h": 20}]}
        r = core.analyse(d)
        self.assertEqual(r["base_unit"]["verdict"], "ambiguous"); self.assertIn(4, r["base_unit"]["competing"])
    def test_validation_errors(self):
        bad = {"schema_version": 2, "unit": "em", "zoom": 0, "frame": {}, "elements": [{"id": "a", "x": "1"}, {"id": "a"}]}
        with self.assertRaises(core.FixtureError) as cm: core.validate(bad)
        self.assertGreaterEqual(len(cm.exception.args[0]), 5)
    def test_deterministic_outputs(self):
        d = fixtures.card_8px(); r1 = core.analyse(d); r2 = core.analyse(fixtures.card_8px())
        self.assertEqual(core.dumps(r1), core.dumps(r2)); self.assertEqual(core.svg_overlay(d, r1), core.svg_overlay(d, r2))
    def test_svg_palette(self):
        d = fixtures.misaligned(); s = core.svg_overlay(d, core.analyse(d))
        self.assertIn("#f3f1f6", s); self.assertIn("#c97a98", s)
    def test_cli(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([sys.executable, "-m", "gridx", "fixtures", td], cwd=root, check=True)
            p = subprocess.run([sys.executable, "-m", "gridx", "analyse", os.path.join(td, "card-8px.json"), "--css", os.path.join(td, "t.css")], cwd=root, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(p.stdout)["tokens"]["space.base"], "8px")
            self.assertIn("--grid-pitch: 112px;", open(os.path.join(td, "t.css")).read())
            json.dump({"unit": "px"}, open(os.path.join(td, "bad.json"), "w"))
            q = subprocess.run([sys.executable, "-m", "gridx", "validate", os.path.join(td, "bad.json")], cwd=root, capture_output=True, text=True)
            self.assertEqual(q.returncode, 2)

if __name__ == "__main__":
    unittest.main()
