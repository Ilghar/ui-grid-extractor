import copy, json, os, subprocess, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gridx.tokens import TokenCheck

TOKENS = os.path.join(ROOT, "fixtures", "ilghar_studio_DESIGN_TOKENS.json")
CARD = os.path.join(ROOT, "fixtures", "tokens-card.json")

def card():
    with open(CARD, encoding="utf-8") as fh:
        return json.load(fh)

class TokenCheckTests(unittest.TestCase):
    def setUp(self):
        self.tokens = TokenCheck.load_tokens(TOKENS)

    def test_palette_and_fonts_come_from_the_tokens_file(self):
        pal = TokenCheck.palette(self.tokens)
        self.assertIn("#c97a98", pal); self.assertIn("#e8a8bc", pal); self.assertIn("#4a434c", pal)
        self.assertEqual(TokenCheck.font_families(self.tokens), {"Jost", "Nunito Sans"})

    def test_tailwind_step_is_4px_default(self):
        self.assertEqual(TokenCheck.TAILWIND_DEFAULT_SPACING_PX, 4)

    def test_pass_case(self):
        r = TokenCheck.check(card(), self.tokens)
        self.assertTrue(r["ok"], r); self.assertEqual(r["errors"], [])

    def test_off_palette_colour_fails(self):
        d = card(); d["elements"][1]["color"] = "#000000"
        r = TokenCheck.check(d, self.tokens)
        self.assertFalse(r["ok"])
        self.assertEqual([(e["id"], e["rule"], e["field"]) for e in r["errors"]], [("title", "colour", "color")])

    def test_colour_case_and_shorthand_normalised(self):
        d = card(); d["elements"][1]["color"] = "#4A3A5C"
        self.assertTrue(TokenCheck.check(d, self.tokens)["ok"])
        d["elements"][1]["color"] = "#fff"
        self.assertFalse(TokenCheck.check(d, self.tokens)["ok"])

    def test_wrong_font_fails(self):
        d = card(); d["elements"][2]["font_family"] = "Helvetica, Jost"
        r = TokenCheck.check(d, self.tokens)
        self.assertEqual([(e["id"], e["rule"]) for e in r["errors"]], [("body", "font")])

    def test_off_step_spacing_fails(self):
        d = card(); d["elements"][3]["y"] = 242; d["elements"][3]["w"] = 130
        r = TokenCheck.check(d, self.tokens)
        self.assertEqual(sorted((e["id"], e["field"]) for e in r["errors"] if e["rule"] == "spacing"),
                         [("button", "w"), ("button", "y")])

    def test_cli_pass_and_fail_exit_codes(self):
        run = lambda p: subprocess.run([sys.executable, "-m", "gridx", "tokens", p, "--tokens", TOKENS],
                                        cwd=ROOT, capture_output=True, text=True)
        ok = run(CARD); self.assertEqual(ok.returncode, 0, ok.stderr); self.assertTrue(json.loads(ok.stdout)["ok"])
        import tempfile
        d = card(); d["elements"][0]["background"] = "#ffffff"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(d, fh)
        try:
            bad = run(fh.name); self.assertEqual(bad.returncode, 1); self.assertFalse(json.loads(bad.stdout)["ok"])
        finally:
            os.unlink(fh.name)

if __name__ == "__main__":
    unittest.main()

class CodexReviewFixes(unittest.TestCase):
    def setUp(self):
        self.tokens = TokenCheck.load_tokens(TOKENS)

    def test_invalid_unit_or_zoom_is_an_input_error(self):
        import tempfile
        for bad in ({"zoom": 0}, {"zoom": "2"}, {"zoom": float("inf")}, {"unit": "em"}):
            d = card(); d.update(bad)
            with self.assertRaises(ValueError):
                TokenCheck.check(d, self.tokens)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                fh.write(json.dumps(d).replace("Infinity", "1e999"))
            r = subprocess.run([sys.executable, "-m", "gridx", "tokens", fh.name, "--tokens", TOKENS],
                               cwd=ROOT, capture_output=True, text=True)
            os.unlink(fh.name)
            self.assertEqual(r.returncode, 2, (bad, r.stderr))
            self.assertIn("invalid input", r.stdout)

    def test_font_family_match_is_case_insensitive(self):
        d = card(); d["elements"][2]["font_family"] = "nunito sans, sans-serif"
        self.assertNotIn("font", [e["rule"] for e in TokenCheck.check(d, self.tokens)["errors"]])
        d["elements"][2]["font_family"] = "helvetica, sans-serif"
        self.assertIn("font", [e["rule"] for e in TokenCheck.check(d, self.tokens)["errors"]])

class CodexReviewFixes2(unittest.TestCase):
    def setUp(self):
        self.tokens = TokenCheck.load_tokens(TOKENS)

    def test_invalid_or_missing_geometry_is_reported(self):
        for bad in ("242", None, False):
            d = card(); d["elements"][0]["x"] = bad
            r = TokenCheck.check(d, self.tokens)
            self.assertFalse(r["ok"]); self.assertIn("geometry", [e["rule"] for e in r["errors"]])
        d = card(); del d["elements"][0]["w"]
        self.assertIn("geometry", [e["rule"] for e in TokenCheck.check(d, self.tokens)["errors"]])

    def test_tiny_coordinate_may_round_to_zero(self):
        from gridx import core, fixtures
        d = fixtures.card_8px(); d["elements"][0]["x"] = 0.00001
        self.assertEqual(core.Bounds.after_normalise(d), [])
        d["elements"][0]["w"] = 0.00001
        self.assertTrue(core.Bounds.after_normalise(d))
