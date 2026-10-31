import copy, io, json, os, sys, unittest
from contextlib import redirect_stdout
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gridx.tokens import TokenCheck
from gridx.__main__ import main

TOKENS = os.path.join(ROOT, "fixtures", "ilghar_studio_DESIGN_TOKENS.json")
CARD = os.path.join(ROOT, "fixtures", "tokens-card.json")
def card():
    with open(CARD, encoding="utf-8") as fh: return json.load(fh)
def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf): code = main(list(argv))
    return code, json.loads(buf.getvalue())

class TokensInputErrors(unittest.TestCase):
    def test_missing_file_matches_validate(self):
        v = run("validate", "/nonexistent-file"); t = run("tokens", "/nonexistent-file")
        self.assertEqual(t[0], v[0]); self.assertEqual(t[0], 2)
        self.assertFalse(t[1]["valid"]); self.assertTrue(t[1]["errors"][0].startswith("cannot read input:"))
    def test_malformed_json_is_an_input_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "bad.json"); open(p, "w").close()
            self.assertEqual(run("tokens", p)[0], 2)
            self.assertEqual(run("tokens", "--tokens", p, CARD)[0], 2)

class TokensUnitConversion(unittest.TestCase):
    def setUp(self): self.tokens = TokenCheck.load_tokens(TOKENS)
    def scaled(self, unit=None, zoom=None, k=1.0):
        d = card()
        for e in d["elements"]:
            for f in ("x", "y", "w", "h"): e[f] = e[f] * k
        if unit: d["unit"] = unit
        if zoom: d["zoom"] = zoom
        return d
    def test_pt_layout_is_converted_before_the_4px_check(self):
        r = TokenCheck.check(self.scaled("pt", k=0.75), self.tokens); self.assertTrue(r["ok"], r)
    def test_mm_layout_is_converted_before_the_4px_check(self):
        r = TokenCheck.check(self.scaled("mm", k=25.4 / 96), self.tokens); self.assertTrue(r["ok"], r)
    def test_zoom_divides_measurements(self):
        r = TokenCheck.check(self.scaled(zoom=2, k=2), self.tokens); self.assertTrue(r["ok"], r)
        r = TokenCheck.check(self.scaled(zoom=2), self.tokens)  # 24 at zoom 2 = 12px: fine; 40 -> 20 ok; check an off value
        d = self.scaled(zoom=2, k=2); d["elements"][0]["x"] = 50  # 25px
        self.assertFalse(TokenCheck.check(d, self.tokens)["ok"])
    def test_off_step_pt_value_still_fails(self):
        d = self.scaled("pt", k=0.75); d["elements"][0]["x"] = 19  # 25.33px
        self.assertFalse(TokenCheck.check(d, self.tokens)["ok"])

class TokensFixtureIsHousePalette(unittest.TestCase):
    """Values from the ilghar.studio site src/styles.css on the PR #1 branch (round 3)."""
    def test_dark_tokens(self):
        dark = TokenCheck.load_tokens(TOKENS)["dark"]
        self.assertEqual((dark["subtle"], dark["accent_fg"], dark["line"]), ("#cbbdce", "#4a434c", "#a394ae"))
    def test_light_accent_fg_is_the_site_value(self):
        self.assertEqual(TokenCheck.load_tokens(TOKENS)["light"]["accent_fg"], "#fffafc")
    def test_no_retired_dark_values(self):
        pal = TokenCheck.palette(TokenCheck.load_tokens(TOKENS))
        self.assertFalse(pal & {"#9a8a9c", "#2c262f", "#4a424c"}, pal)

if __name__ == "__main__": unittest.main()
