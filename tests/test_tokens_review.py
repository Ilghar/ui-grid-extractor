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


class TokensElementsShape(unittest.TestCase):
    def setUp(self): self.tokens = TokenCheck.load_tokens(TOKENS)
    def test_invalid_collections_are_input_errors(self):
        import tempfile
        for layout in ({}, {"elements": None}, {"elements": []}, {"elements": [None]}, {"elements": "x"}, []):
            with self.subTest(layout=layout):
                with self.assertRaises(ValueError): TokenCheck.check(layout, self.tokens)
                with tempfile.TemporaryDirectory() as td:
                    p = os.path.join(td, "l.json"); open(p, "w").write(json.dumps(layout))
                    code, out = run("tokens", "--tokens", TOKENS, p)
                    self.assertEqual(code, 2); self.assertFalse(out["valid"])
                    self.assertTrue(out["errors"][0].startswith("invalid input:"))
    def test_valid_card_still_checks(self):
        self.assertEqual(TokenCheck.check(card(), self.tokens)["checked"], len(card()["elements"]))


class TokensValueShapes(unittest.TestCase):
    def setUp(self): self.tokens = TokenCheck.load_tokens(TOKENS)
    def test_non_string_font_family_is_a_font_violation(self):
        for bad in (None, 3, ["Jost"], {}):
            with self.subTest(bad=bad):
                d = card(); d["elements"][0]["font_family"] = bad
                r = TokenCheck.check(d, self.tokens)
                self.assertFalse(r["ok"])
                self.assertIn("font", [e["rule"] for e in r["errors"]])
    def test_invalid_token_file_is_an_input_error(self):
        import tempfile
        good = TokenCheck.load_tokens(TOKENS)
        bads = [{}, [], {"light": None, "dark": {}, "fonts": {}},
                dict(good, fonts={"sans": None, "display": "Jost"}), dict(good, fonts={"sans": "Jost"}), dict(good, dark=None)]
        for toks in bads:
            with self.subTest(toks=str(toks)[:60]):
                with self.assertRaises(ValueError): TokenCheck.check(card(), toks)
                with tempfile.TemporaryDirectory() as td:
                    t = os.path.join(td, "t.json"); open(t, "w").write(json.dumps(toks))
                    l = os.path.join(td, "l.json"); open(l, "w").write(json.dumps(card()))
                    code, out = run("tokens", "--tokens", t, l)
                    self.assertEqual(code, 2); self.assertFalse(out["valid"])


class CodexReview6589193881(unittest.TestCase):
    def setUp(self):
        import json as _j, os as _o
        root = _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__)))
        from gridx.tokens import TokenCheck
        self.TC, self.tokens = TokenCheck, TokenCheck.load_tokens(_o.path.join(root, "fixtures", "ilghar_studio_DESIGN_TOKENS.json"))
        self.card = lambda: _j.load(open(_o.path.join(root, "fixtures", "tokens-card.json"), encoding="utf-8"))

    def _rules(self, d):
        r = self.TC.check(d, self.tokens); return r["ok"], [e["rule"] for e in r["errors"]]

    def test_negative_position_and_zero_size_are_rejected(self):
        for f, v in (("x", -4), ("y", -8), ("w", 0), ("h", 0)):
            d = self.card(); d["elements"][0][f] = v
            ok, rules = self._rules(d)
            self.assertFalse(ok); self.assertIn("geometry", rules)
        d = self.card(); d["elements"][0]["x"] = 0
        self.assertTrue(self._rules(d)[0])

    def test_conversion_overflow_is_rejected_and_output_is_standard_json(self):
        import json as _j
        d = self.card(); d["unit"] = "mm"; d["zoom"] = 0.015625; d["elements"][0]["x"] = 1e308
        r = self.TC.check(d, self.tokens)
        self.assertFalse(r["ok"]); self.assertIn("geometry", [e["rule"] for e in r["errors"]])
        _j.dumps(r, allow_nan=False)


class CodexP2FollowUp(unittest.TestCase):
    def _check(self, field, value):
        import copy
        from gridx import fixtures
        from gridx.tokens import TokenCheck
        lay = copy.deepcopy(fixtures.card_8px())
        lay["elements"][0][field] = value
        return TokenCheck.check(lay, TokenCheck.load_tokens(TOKENS))

    def test_size_rounding_to_zero_is_rejected(self):
        r = self._check("w", 0.00001)
        self.assertFalse(r["ok"])

    def test_nonfinite_value_is_serialised_as_standard_json(self):
        import json
        r = self._check("w", float("inf"))
        self.assertFalse(r["ok"])
        json.dumps(r, allow_nan=False)
