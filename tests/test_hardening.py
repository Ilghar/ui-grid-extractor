import json, os, subprocess, sys, tempfile, unittest
import xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gridx import core, fixtures
from gridx.svgsrc import parse_svg


def _errs(d):
    try:
        core.validate(d); return []
    except core.FixtureError as e:
        return e.args[0]


def _cli(*args):
    return subprocess.run([sys.executable, "-m", "gridx", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)


class Normalisation(unittest.TestCase):
    def test_font_size_rounding_to_zero_is_error_not_crash(self):
        d = fixtures.card_8px(); d["elements"][3]["font_size"] = 1e-5
        self.assertTrue(any("font_size" in e for e in _errs(d)))
    def test_size_rounding_to_zero_is_error_not_exact(self):
        d = fixtures.card_8px(); d["elements"][0]["w"] = 1e-5
        self.assertTrue(any(".w" in e for e in _errs(d)))
    def test_overflow_after_conversion_is_error(self):
        d = fixtures.card_8px(); d["unit"] = "pt"; d["elements"][0]["x"] = 1.7e308
        self.assertTrue(any(".x" in e for e in _errs(d)))


class Overlay(unittest.TestCase):
    def test_ids_are_escaped(self):
        d = fixtures.card_8px(); d["elements"][0]["id"] = 'a"/><script>x</script>&'
        s = core.svg_overlay(d, core.analyse(d))
        ET.fromstring(s)  # well-formed
        self.assertNotIn("<script>", s)
    def test_rtl_id_is_bidi_isolated(self):
        d = fixtures.misaligned(); d["elements"][0]["id"] = "\u05db\u05e8\u05d8\u05d9\u05e1"
        s = core.svg_overlay(d, core.analyse(d))
        self.assertIn("\u2068\u05db\u05e8\u05d8\u05d9\u05e1\u2069", s)
    def test_huge_frame_does_not_hang(self):
        d = fixtures.card_8px(); d["frame"]["height"] = 1e9
        s = core.svg_overlay(d, core.analyse(d))
        self.assertLess(s.count("<line"), 10000)


class Cli(unittest.TestCase):
    def test_malformed_svg_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "bad.svg"); open(f, "w").write("<svg")
            p = _cli("analyse", "--from-svg", f)
            self.assertEqual(p.returncode, 2); self.assertNotIn("Traceback", p.stderr)
            self.assertIn("cannot read input", p.stdout)
    def test_malformed_svg_is_value_error(self):
        with self.assertRaises(ValueError): parse_svg("<svg")
    def test_unwritable_output_exits_2(self):
        for flag in ("--svg", "--css"):
            p = _cli("analyse", os.path.join(ROOT, "fixtures", "card-8px.json"), flag, "/nonexistent-dir/out")
            self.assertEqual(p.returncode, 2, flag); self.assertNotIn("Traceback", p.stderr)
            self.assertIn("cannot write output", p.stdout)


if __name__ == "__main__":
    unittest.main()
