"""Check a layout's colours, font families and spacing against the ilghar.studio design tokens.

Colours and font families come from DESIGN_TOKENS.json (the studio's src/styles.css).
Spacing is NOT a studio token: the studio site uses Tailwind CSS v4 without overriding
--spacing, so spacing is checked against Tailwind's default step of 0.25rem = 4px.
"""
import json, re
from .core import UNITS_TO_PX, MIN_ZOOM, MAX_ZOOM, _isnum

class TokenCheck:
    TAILWIND_DEFAULT_SPACING_PX = 4  # Tailwind v4 default --spacing (0.25rem at 16px), not a studio token
    SPACING_FIELDS = ("x", "y", "w", "h")
    COLOUR_FIELDS = ("color", "background", "border_color")
    _HEX = re.compile(r"^#[0-9a-f]{6}$")

    @staticmethod
    def load_tokens(path):
        with open(path, encoding="utf-8") as fh:
            tokens = json.load(fh)
        TokenCheck.validate_tokens(tokens)
        return tokens

    @staticmethod
    def validate_tokens(tokens):
        # a token file must have light/dark colour objects and sans/display font-stack strings
        if not isinstance(tokens, dict):
            raise ValueError("token file must be a JSON object (got %s)" % type(tokens).__name__)
        for theme in ("light", "dark"):
            if not isinstance(tokens.get(theme), dict):
                raise ValueError("token file: %r must be an object of colours (got %r)" % (theme, tokens.get(theme)))
        fonts = tokens.get("fonts")
        if not isinstance(fonts, dict):
            raise ValueError("token file: 'fonts' must be an object (got %r)" % (fonts,))
        for k in ("sans", "display"):
            if not isinstance(fonts.get(k), str) or not TokenCheck.first_family(fonts[k]):
                raise ValueError("token file: fonts.%s must be a non-empty font-stack string (got %r)" % (k, fonts.get(k)))

    @staticmethod
    def palette(tokens):
        return {v.lower() for theme in ("light", "dark") for v in tokens[theme].values()
                if isinstance(v, str) and TokenCheck._HEX.match(v.lower())}

    @staticmethod
    def first_family(stack):
        return stack.split(",")[0].strip().strip("'\"").strip()

    @staticmethod
    def font_families(tokens):
        return {TokenCheck.first_family(tokens["fonts"][k]) for k in ("sans", "display")}

    @staticmethod
    def check(layout, tokens, step=None):
        step = step or TokenCheck.TAILWIND_DEFAULT_SPACING_PX
        TokenCheck.validate_tokens(tokens)
        # same shape rule as core validation: an object with a non-empty list of element objects
        if not isinstance(layout, dict):
            raise ValueError("layout must be a JSON object (got %s)" % type(layout).__name__)
        elements = layout.get("elements")
        if not isinstance(elements, list) or not elements:
            raise ValueError("elements must be a non-empty list (got %r)" % (elements,))
        bad = [i for i, el in enumerate(elements) if not isinstance(el, dict)]
        if bad:
            raise ValueError("elements[%d] must be an object" % bad[0])
        # same conversion as core.normalise: unit -> CSS px, divided by zoom, rounded to 4 dp
        unit, zoom = layout.get("unit", "px"), layout.get("zoom", 1.0)
        if not isinstance(unit, str) or unit not in UNITS_TO_PX:
            raise ValueError("unit must be one of px, pt, mm (got %r)" % (unit,))
        if not _isnum(zoom) or not (MIN_ZOOM <= zoom <= MAX_ZOOM):
            raise ValueError("zoom must be a finite number in [1/64, 64] (got %r)" % (zoom,))
        factor = UNITS_TO_PX[unit] / float(zoom)
        pal, fams, errors = TokenCheck.palette(tokens), TokenCheck.font_families(tokens), []
        fams_ci = {f.casefold() for f in fams}  # CSS font-family names are case-insensitive
        for el in elements:
            eid = el.get("id", "?")
            for f in TokenCheck.COLOUR_FIELDS:
                if f in el and str(el[f]).lower() not in pal:
                    errors.append({"id": eid, "rule": "colour", "field": f, "value": el[f], "expected": "a colour from DESIGN_TOKENS.json light/dark"})
            if "font_family" in el and (not isinstance(el["font_family"], str)
                                        or TokenCheck.first_family(el["font_family"]).casefold() not in fams_ci):
                errors.append({"id": eid, "rule": "font", "field": "font_family", "value": el["font_family"], "expected": sorted(fams)})
            for f in TokenCheck.SPACING_FIELDS:
                v = el.get(f)
                if not _isnum(v):
                    errors.append({"id": eid, "rule": "geometry", "field": f, "value": v, "expected": "a finite number"})
                elif round(v * factor, 4) % step:
                    errors.append({"id": eid, "rule": "spacing", "field": f, "value": v, "value_px": round(v * factor, 4), "expected": "multiple of %gpx (Tailwind default step)" % step})
        return {"ok": not errors, "errors": errors, "checked": len(elements),
                "spacing_step_px": step, "spacing_source": "Tailwind CSS default --spacing, not a studio token"}
