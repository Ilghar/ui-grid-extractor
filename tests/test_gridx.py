import json, os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gridx import core, fixtures, verify

class T(unittest.TestCase):
    def test_verify_all(self):
        r = verify.run(); self.assertEqual(r["passed"], r["total"], r)
    def test_no_default_grid(self):
        d = {"schema_version": 1, "unit": "px", "frame": {"width": 100, "height": 100}, "tolerance": 0.2,
             "elements": [{"id": "a", "x": 7.3, "y": 11.1, "w": 33.7, "h": 9.9}, {"id": "b", "x": 41.3, "y": 27.7, "w": 13.1, "h": 5.3}, {"id": "c", "x": 3.9, "y": 61.3, "w": 21.7, "h": 17.1}]}
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
        d["frame"] = {"width": 376 * f, "height": 400 * f}; d["unit"] = "mm"; d["tolerance"] = 0.1
        self.assertEqual(core.analyse(d)["base_unit"]["base_px"], 8)
    def test_ambiguous_preserved(self):
        r = core.analyse(fixtures.rhythm_5px())
        self.assertEqual(r["base_unit"]["base_px"], 5)
        d = {"schema_version": 1, "unit": "px", "frame": {"width": 100, "height": 100},
             "elements": [{"id": "a", "x": 20, "y": 40, "w": 60, "h": 80}, {"id": "b", "x": 100, "y": 140, "w": 40, "h": 20}, {"id": "c", "x": 20, "y": 180, "w": 120, "h": 20}]}
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
        self.assertIn("#f3f1f6", s); self.assertIn("#856a8e", s)
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

def _errs(d):
    try:
        core.validate(d); return []
    except core.FixtureError as e:
        return e.args[0]


class Adversarial(unittest.TestCase):
    def base(self):
        return fixtures.card_8px()
    def test_nan_is_error_not_exact(self):
        d = self.base(); d["elements"][0]["x"] = float("nan")
        self.assertTrue(any("finite" in e for e in _errs(d)))
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "nan.json")
            open(f, "w").write(core.dumps(self.base()).replace('"x": 24,', '"x": NaN,', 1))
            p = subprocess.run([sys.executable, "-m", "gridx", "analyse", f], cwd=root, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2); self.assertNotIn('"exact": true', p.stdout)
    def test_negative_is_error(self):
        d = self.base(); d["elements"][0]["y"] = -8
        self.assertTrue(any(">= 0" in e for e in _errs(d)))
    def test_non_string_unit(self):
        d = self.base(); d["unit"] = ["px"]
        self.assertTrue(any("unit" in e for e in _errs(d)))
    def test_missing_and_bad_files(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "bad.json"); open(bad, "w").write("{not json")
            for f in (os.path.join(td, "missing.json"), bad):
                p = subprocess.run([sys.executable, "-m", "gridx", "analyse", f], cwd=root, capture_output=True, text=True)
                self.assertEqual(p.returncode, 2); self.assertNotIn("Traceback", p.stderr)
                self.assertIn("cannot read input", p.stdout)
    def test_tolerance_bounded(self):
        for tol in (100, 1.0, True, float("nan"), float("inf"), -1):
            d = self.base(); d["tolerance"] = tol
            self.assertTrue(_errs(d), tol)
    def test_bools_rejected(self):
        for path in (("frame", "width"), ("schema_version",), ("font_size",)):
            d = self.base()
            if path[0] == "frame": d["frame"]["width"] = True
            elif path[0] == "font_size": d["elements"][3]["font_size"] = True
            else: d["schema_version"] = True
            self.assertTrue(_errs(d), path)
    def test_zoom_bounds(self):
        for z in (float("inf"), 1e-320, 0, True):
            d = self.base(); d["zoom"] = z
            self.assertTrue(any("zoom" in e for e in _errs(d)), z)
    def test_min_evidence_columns(self):
        d = {"schema_version": 1, "unit": "px", "frame": {"width": 50, "height": 50},
             "elements": [{"id": "a", "x": 1, "y": 0, "w": 4, "h": 4}, {"id": "b", "x": 3, "y": 8, "w": 4, "h": 4},
                          {"id": "c", "x": 1, "y": 16, "w": 4, "h": 4}]}
        r = core.analyse(d)
        self.assertFalse(r["columns"]["regular"]); self.assertNotIn("grid.pitch", r["tokens"])
        self.assertEqual(r["columns"]["evidence"], "insufficient")
    def test_min_evidence_base(self):
        d = {"schema_version": 1, "unit": "px", "frame": {"width": 50, "height": 50},
             "elements": [{"id": "a", "x": 0, "y": 0, "w": 48, "h": 48}]}
        r = core.analyse(d)
        self.assertEqual(r["base_unit"]["verdict"], "insufficient"); self.assertFalse(r["exact"])


class Grouping(unittest.TestCase):
    def test_order_independent_and_no_chaining(self):
        import random
        d = fixtures.card_8px()
        for e in d["elements"][3:]:
            e["x"] = 24.4  # within tol of 24 but near the old tol/2 boundary
        base = core.dumps(core.analyse(d)["columns"])
        for seed in range(5):
            random.Random(seed).shuffle(d["elements"])
            self.assertEqual(core.dumps(core.analyse(d)["columns"]), base)
        n = {"tolerance": 0.5, "elements": [{"id": str(i), "x": v} for i, v in enumerate([0, 0.4, 0.8, 1.2])]}
        self.assertEqual(len(core.columns(n)["guides_px"]), 2)  # chain 0..1.2 no longer collapses into one guide


class Themes(unittest.TestCase):
    def test_contrast_both_themes(self):
        for name, T in core.THEMES.items():
            self.assertGreaterEqual(core.contrast(T["ink"], T["canvas"]), 4.5, name)    # labels + strokes
            self.assertGreaterEqual(core.contrast(T["muted"], T["canvas"]), 3.0, name)  # large text only: studio light muted is 4.47:1
    def test_overlay_theme_option(self):
        d = fixtures.misaligned(); r = core.analyse(d)
        dark = core.svg_overlay(d, r, "dark"); light = core.svg_overlay(d, r, "light")
        self.assertIn('data-theme="dark"', dark); self.assertIn("#473448", dark); self.assertIn("#f3f1f6", light)
        self.assertIn("misaligned", dark)  # flag is text, not hue-only
        with self.assertRaises(ValueError): core.svg_overlay(d, r, "sepia")


if __name__ == "__main__":
    unittest.main()
