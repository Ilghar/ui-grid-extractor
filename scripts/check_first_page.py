#!/usr/bin/env python3
"""First-page CI (layout v2 / SÁBÁT standard): CSS frame radius 12px,
column 100%/720/760, type scale 24/31 · 23 · 13, fonts Jost/Vazirmatn only,
off-palette #hex in source, blue pixels (and blue hex in SVG).

Frame radius is enforced in CSS on .panel / .frame / .card / .ilg-frame only.
SVG/PNG art is not checked for radius (images ship square; the 12px frame
with overflow:hidden rounds them).

Soft control shadows from tokens.css are allowed. Frames themselves must
not have a drop shadow.

Approved pink tokens (#fcb4c4, #b78597, #da94af, #745a7a and the --pink / --pink-mark-* /
--pink-fill-dark variables) may be used anywhere. They are palette colours, not tints.
FAIL: off-palette pinks, and pink with opacity/alpha, color-mix, or rgba tints.
Pink text must reach 4.5:1 against its background when the script can resolve both
hexes; large text and marks (24px / 18pt, .first, .dc, h1) must reach 3:1.
Hāèl's 12 Nov 2026 (15:31) values: first letters and pink marks #b78597 (about 2.9:1 on paper, large or decorative, not AA). Small text under ~18px, and first letters on Signature-animation glass #b8adb1, use mauve #856a8e. Glass accents #da94af. Dark Sign / Live fill #745a7a. Dark marks stay #fcb4c4. Do not put #b78597 on #b8adb1 (about 1.4:1).
A heading (h1-h6) whose whole text is an approved pink FAILs; only the first letter may be pink.
Walnut #5b4032 is in the palette. The blue rule and the photo allowlist are unchanged.

Dark mode: the --name title (h1/.name, 24px+) after the pink first letter
must be #856a8e / var(--mauve-em). Headings under 24px (h2 at 23px, etc.)
are not checked for this colour.

Photo boards named disagreement or fact-vs-taste are palette-allowlisted
(off-palette colours are ignored) but still run the blue check.

Content images need a light and a dark file, served through <picture> with
a prefers-color-scheme dark source (and swapped by the theme toggle).
A content <img> with no dark source FAILs. Favicons and app icons are skipped.
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import io
import re
import sys
import warnings
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "first-page-allowlist.txt"
TOKENS_CANDIDATES = [
    ROOT / "site" / "tokens.css",
    ROOT / "tokens.css",
    ROOT / "public" / "design" / "tokens.css",
    ROOT / "src" / "tokens-first-page.css",
]

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
TEXT_EXT = {".css", ".html", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".svg"}
SKIP_DIRS = {".git", "node_modules", "dist", "vendor", "__pycache__", ".venv", "pr-shots"}

FALLBACK_HEX = {
    "#f9fafb", "#5a515c", "#473448", "#856a8e", "#7d5a7c", "#775a76",
    "#948e95", "#a6a1a7", "#fcb4c4", "#b78597", "#da94af", "#745a7a", "#5b4032",
    "#2a272d", "#d4d2d2",
}

APPROVED_PINKS = {"#fcb4c4", "#b78597", "#da94af", "#745a7a"}
APPROVED_PINK_RGB = {
    "#fcb4c4": (0xFC, 0xB4, 0xC4),
    "#b78597": (0xB7, 0x85, 0x97),
    "#da94af": (0xDA, 0x94, 0xAF),
    "#745a7a": (0x74, 0x5A, 0x7A),
}
APPROVED_PINK_VARS = {
    "pink", "pink-mark-light", "pink-mark-dark", "pink-fill-dark", "pink-glass", "glass-accent", "dc", "ring",
}
PINK = "#fcb4c4"
PINK_RGB = (0xFC, 0xB4, 0xC4)

def _is_siganim_repo() -> bool:
    return ROOT.name.lower() == "signature-animation"


GENERIC_FONTS = {"sans-serif", "serif", "monospace", "inherit", "initial", "unset"}
NAMED_FONTS = {"jost", "vazirmatn"}

# v2 frame radius
FRAME_RADIUS_OK = re.compile(
    r"^(var\(--r-frame(?:,\s*12px)?\)|12px)(\s+(var\(--r-frame(?:,\s*12px)?\)|12px)){0,3}$",
    re.I,
)

FONT_FAMILY_CSS = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.I)
FONT_FAMILY_ATTR = re.compile(r"font-family\s*=\s*[\"']([^\"']+)[\"']", re.I)
FONT_SHORTHAND = re.compile(
    r"font\s*:\s*(?:(?:normal|italic|oblique|bold|bolder|lighter|\d{3})\s+)*"
    r"[\d.]+(?:px|rem|em|%)?(?:\s*/\s*[\d.]+(?:px|rem|em|%|))?\s+([^;}\"']+)",
    re.I,
)
FONT_WEIGHT = re.compile(r"font-weight\s*:\s*([^;}\n]+)", re.I)
BAD_WEIGHT = re.compile(r"^(500|600|700|800|900|bold|bolder)(\s*!important)?$", re.I)
WEIGHT_VAR_DEF = re.compile(
    r"--[a-z0-9-]*weight[a-z0-9-]*\s*:\s*(500|600|700|800|900|bold|bolder)\b",
    re.I,
)
BORDER_RADIUS = re.compile(r"border-radius\s*:\s*([^;}\n]+)", re.I)
BOX_SHADOW = re.compile(r"box-shadow\s*:\s*([^;}\n]+)", re.I)

ILLUSTRATION_SVG = re.compile(
    r"(?:^|/)(?:docs/hero/|assets/)?(?:hero|board|og|illustration|mark)[^/]*\.svg$",
    re.I,
)

PALETTE_ONLY_NAME = re.compile(
    r"(?:^|/)(?:disagreement|fact-vs-taste|fact_vs_taste)(?:\.[a-z0-9]+)?$",
    re.I,
)

GOOGLE_FONT = re.compile(
    r"https://fonts\.googleapis\.com/css2\?[^\"'\s)>]+",
    re.I,
)


def load_allowed_hex() -> set[str]:
    allowed = {h.lower() for h in FALLBACK_HEX}
    for p in TOKENS_CANDIDATES:
        if p.exists():
            found = set(
                h.lower()
                for h in re.findall(r"#[0-9A-Fa-f]{6}\b", p.read_text(encoding="utf-8", errors="ignore"))
            )
            if found:
                allowed |= found
                break
    return allowed


ALLOWED_HEX = load_allowed_hex()


def expand(h: str) -> str:
    h = h.lower()
    if len(h) == 4:
        return "#" + "".join(c * 2 for c in h[1:])
    if len(h) == 9:
        return "#" + h[1:7]
    return h


def near_allowed(r: int, g: int, b: int, tol: int = 18) -> bool:
    hx = "#{:02x}{:02x}{:02x}".format(r, g, b)
    if hx in ALLOWED_HEX:
        return True
    for ah in ALLOWED_HEX:
        ar, ag, ab = int(ah[1:3], 16), int(ah[3:5], 16), int(ah[5:7], 16)
        if abs(ar - r) + abs(ag - g) + abs(ab - b) <= tol:
            return True
    return False


def is_pink_tint(r: int, g: int, b: int) -> bool:
    """Pinkish hue that is not an approved pink token."""
    if (r, g, b) in APPROVED_PINK_RGB.values():
        return False
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue = h * 360.0
    if s < 0.15 or v < 0.35:
        return False
    return (hue >= 320 or hue <= 20)


def rgb_to_hue_sat(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s, v


def is_blue_rgb(r: int, g: int, b: int) -> bool:
    hue, sat, val = rgb_to_hue_sat(r, g, b)
    return 190 <= hue <= 250 and sat > 0.25 and val > 0.12


def load_allowlist() -> tuple[set[str], set[str]]:
    """Return (full_skip, palette_only) path sets."""
    full: set[str] = set()
    palette: set[str] = set()
    if not ALLOWLIST.exists():
        return full, palette
    for raw in ALLOWLIST.read_text().splitlines():
        stripped = raw.split("#", 1)
        note = stripped[1].strip().lower() if len(stripped) > 1 else ""
        line = stripped[0].strip()
        if not line:
            # allow `# palette-only path`? no, comments only
            continue
        kind = None
        if line.lower().startswith("palette-only "):
            kind, line = "palette", line.split(" ", 1)[1].strip()
        elif line.lower().startswith("palette "):
            kind, line = "palette", line.split(" ", 1)[1].strip()
        if "palette-only" in note or note.startswith("palette"):
            kind = "palette"
        path = line.replace("\\", "/")
        if not path:
            continue
        (palette if kind == "palette" else full).add(path)
    return full, palette


def _match_allow(path: Path, allow: set[str]) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in allow:
        return True
    for a in allow:
        if a.endswith("/") and rel.startswith(a):
            return True
        if rel == a or rel.startswith(a.rstrip("/") + "/"):
            return True
    return False


def is_full_allowlisted(path: Path, full: set[str]) -> bool:
    return _match_allow(path, full)


def is_palette_only(path: Path, palette: set[str]) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if PALETTE_ONLY_NAME.search(rel):
        return True
    return _match_allow(path, palette)


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(x in SKIP_DIRS for x in p.parts):
            continue
        yield p


def scan_blue_pixels(im: Image.Image, max_px: int = 2_000_000) -> int:
    im = im.convert("RGBA")
    w, h = im.size
    if w * h > max_px:
        scale = (max_px / (w * h)) ** 0.5
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        px = im.getdata()
    blue = 0
    step = max(1, len(px) // 200_000)
    for i in range(0, len(px), step):
        r, g, b, a = px[i]
        if a < 16:
            continue
        if is_blue_rgb(r, g, b):
            blue += 1
    return blue


def font_parts_ok(family_list: str) -> list[str]:
    bad: list[str] = []
    for n in (x.strip().strip("'\"") for x in family_list.split(",")):
        if not n:
            continue
        low = n.lower()
        if low in GENERIC_FONTS or low in NAMED_FONTS:
            continue
        if re.match(r"^var\(\s*--font", n, re.I):
            continue
        bad.append(n)
    return bad


FONT_TOKEN_DEF = re.compile(r"--font[a-z0-9-]*\s*:\s*([^;}\n]+)", re.I)


def check_fonts(text: str) -> list[str]:
    bad: list[str] = []
    for m in FONT_FAMILY_CSS.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    for m in FONT_FAMILY_ATTR.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    for m in FONT_SHORTHAND.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    for m in FONT_TOKEN_DEF.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    for m in GOOGLE_FONT.finditer(text):
        url = m.group(0)
        # Only Jost and Vazirmatn may be requested, weights 300 and 400 only
        for fam in re.findall(r"family=([^&:]+)", url):
            name = fam.replace("+", " ").lower()
            if name not in {"jost", "vazirmatn"}:
                bad.append("google-font:" + fam.replace("+", " "))
        if re.search(r"wght@[^\"']*(500|600|700|800|900)", url):
            bad.append("google-font-weight:" + url[:80])
    return bad


def check_weights(text: str) -> list[str]:
    bad: list[str] = []
    for m in FONT_WEIGHT.finditer(text):
        val = m.group(1).strip()
        if BAD_WEIGHT.match(val):
            bad.append(f"font-weight:{val}")
    # font: shorthand that starts with a bad weight
    for m in re.finditer(r"font\s*:\s*(500|600|700|800|900|bold|bolder)\b", text, re.I):
        bad.append(f"font-shorthand-weight:{m.group(1)}")
    for m in WEIGHT_VAR_DEF.finditer(text):
        bad.append(f"weight-token:{m.group(0).strip()}")
    return bad


def _strip_css_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def css_rules(text: str):
    text = _strip_css_comments(text)
    for part in text.split("}"):
        if "{" not in part:
            continue
        sel, body = part.rsplit("{", 1)
        sel = sel.strip()
        sel = re.sub(r"^@[^{]*\{", "", sel).strip()
        sel = sel.split("{")[-1].strip()
        if sel:
            yield sel, body


def _subject(part: str) -> str:
    last = re.split(r"\s*[>+~]\s*|\s+", part.strip())[-1]
    last = re.sub(r":{1,2}[\w-]+(\([^)]*\))?", "", last)
    return last


def is_inner_art(part: str) -> bool:
    if re.search(r"(\.frame|\.panel|\.card|\.ilg-frame|\.hero|figure)\s*[>\s]\s*(img|svg|canvas|picture|video)", part, re.I):
        return True
    last = _subject(part)
    return bool(re.match(r"^(img|svg|canvas|picture|video)([.#\[\s]|$)", last, re.I))


def is_frame_subject(part: str) -> bool:
    if is_inner_art(part):
        return False
    last = _subject(part)
    return bool(re.search(r"(^|\.)(panel|frame|card|ilg-frame)(?![\w-])", last, re.I))


def _clean_decl(val: str) -> str:
    return re.sub(r"!important", "", val, flags=re.I).strip()


def check_radius(text: str) -> list[str]:
    """Require 12px / var(--r-frame) on CSS frame selectors. Ignore SVG/PNG art."""
    bad: list[str] = []
    for sel, body in css_rules(text):
        m = BORDER_RADIUS.search(body)
        if not m:
            continue
        val = _clean_decl(m.group(1))
        parts = [p.strip() for p in sel.split(",") if p.strip()]
        if not any(is_frame_subject(p) for p in parts):
            continue
        if not FRAME_RADIUS_OK.match(val):
            bad.append(f"border-radius:{val} on {sel[:80]}")
    return bad


def check_frame_shadows(text: str) -> list[str]:
    """Frames must not have a drop shadow. Control shadows are allowed."""
    bad: list[str] = []
    for sel, body in css_rules(text):
        m = BOX_SHADOW.search(body)
        if not m:
            continue
        val = _clean_decl(m.group(1)).lower()
        parts = [p.strip() for p in sel.split(",") if p.strip()]
        if not any(is_frame_subject(p) for p in parts):
            continue
        if val in {"none", "unset", "initial", "0", "0 0 0 0 transparent"}:
            continue
        bad.append(f"frame-shadow:{val[:80]} on {sel[:80]}")
    return bad


def check_source_hex(text: str) -> list[str]:
    check = re.sub(r"data:image/[^\"']+", "", text)
    bad: list[str] = []
    for h in set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", check)):
        raw = h.lower()
        if len(raw) == 9 and raw[:7] in APPROVED_PINKS:
            bad.append(f"pink-alpha:{raw}")
            continue
        hx = expand(raw)
        if len(hx) != 7:
            continue
        if hx in APPROVED_PINKS:
            continue  # owned by check_pink / contrast
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        if is_pink_tint(r, g, b):
            bad.append(f"pink-tint:{hx}")
            continue
        if not near_allowed(r, g, b):
            bad.append(hx)
    return bad


def check_blue_hex(text: str) -> list[str]:
    """Blue-hued hex in SVG/CSS source (used even on palette-allowlisted art)."""
    check = re.sub(r"data:image/[^\"']+", "", text)
    bad: list[str] = []
    for h in set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", check)):
        hx = expand(h.lower())
        if len(hx) != 7:
            continue
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        if is_blue_rgb(r, g, b):
            bad.append(hx)
    return bad



def _rel_luminance(hx: str) -> float:
    r, g, b = int(hx[1:3], 16) / 255, int(hx[3:5], 16) / 255, int(hx[5:7], 16) / 255

    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _rel_luminance(a), _rel_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _as_hex(val: str) -> str | None:
    val = _norm_css_val(val) if "_norm_css_val" in dir() else val.strip().lower()
    m = re.fullmatch(r"#[0-9a-f]{6}", val)
    return m.group(0) if m else None


def is_approved_pink_hex(hx: str) -> bool:
    return expand(hx).lower() in APPROVED_PINKS


def _pink_alpha_in(ctx: str) -> bool:
    if re.search(r"#(?:fcb4c4|b78597|da94af|745a7a|aa527d)[0-9a-fA-F]{2}\b", ctx, re.I):
        return True
    if re.search(r"color-mix\([^)]*#(?:fcb4c4|b78597|da94af|745a7a|aa527d)", ctx, re.I):
        return True
    if re.search(
        r"rgba?\(\s*(252\s*,\s*180\s*,\s*196|183\s*,\s*133\s*,\s*151|218\s*,\s*148\s*,\s*175|116\s*,\s*90\s*,\s*122|170\s*,\s*82\s*,\s*125)\s*,",
        ctx,
        re.I,
    ):
        return True
    return False


def check_pink(text: str, rel: str) -> list[str]:
    """Approved pink tokens may be used anywhere. Fail only alpha / rgba / color-mix tints."""
    issues: list[str] = []
    if rel.endswith("tokens.css") or rel.endswith("tokens-first-page.css"):
        return issues
    if rel.endswith(".svg") and ILLUSTRATION_SVG.search(rel):
        return issues
    if rel.endswith(".svg") and re.search(r"(?:^|/)(?:docs/hero|assets)/(?:hero|board)", rel):
        return issues

    token_pat = (
        r"#fcb4c4|#b78597|#da94af|#745a7a|"
        r"var\(\s*--(?:pink|pink-mark-light|pink-mark-dark|pink-fill-dark)\s*\)"
    )
    for m in re.finditer(token_pat, text, re.I):
        start = max(0, m.start() - 220)
        end = min(len(text), m.end() + 100)
        ctx = text[start:end]
        if _pink_alpha_in(ctx):
            issues.append(f"pink-alpha near: {ctx.replace(chr(10), ' ')[:90]!r}")
    return issues


def _is_mark_or_large(sel: str, body: str) -> bool:
    if re.search(r"::first-letter|\.first\b|\.dc\b|\.name\b|(^|[^a-z-])h1\b", sel, re.I):
        return True
    sizes = re.findall(r"font-size\s*:\s*([^;}\n]+)", body, re.I)
    for raw in sizes:
        m = re.search(r"([\d.]+)\s*(px|pt)", raw, re.I)
        if not m:
            continue
        n, unit = float(m.group(1)), m.group(2).lower()
        if unit == "px" and n >= 24:
            return True
        if unit == "pt" and n >= 18:
            return True
    return False


def _is_decoration_color_sel(sel: str) -> bool:
    if re.search(r"::(?:before|after)", sel, re.I) and re.search(r"dots|\.dot\b", sel, re.I):
        return True
    return False


def _glass_exception(fg: str, bg: str) -> bool:
    """No pink mark is allowed on Signature-animation glass #b8adb1.
    First letters on that base use mauve #856a8e (not a pink token)."""
    return False


def _paper_mark_exception(fg: str, bg: str) -> bool:
    """Hāèl's 12 Nov 2026 light mark #b78597 is about 2.9:1 on paper #f9fafb.
    Allowed for large or decorative use only; not AA."""
    return fg == "#b78597" and bg == "#f9fafb"


def check_pink_contrast(css: str) -> list[str]:
    """When colour and background hexes can be resolved, require 4.5:1 (body)
    or 3:1 (large text / marks). Exempt #b78597 on #f9fafb for marks (about 2.9:1, not AA). Do not exempt #b78597 on #b8adb1; first letters on that glass use mauve #856a8e."""
    issues: list[str] = []
    text = _strip_css_comments(css)
    light, dark = _theme_vars(text)
    maps = {"light": light, "dark": dark}
    default_bg = {"light": "#f9fafb", "dark": "#2a272d"}

    def bg_for(body: str, theme: str, vm: dict[str, str]) -> str | None:
        bm = re.search(r"background(?:-color)?\s*:\s*([^;}\n]+)", body, re.I)
        if bm:
            hx = _as_hex(_resolve_css_val(bm.group(1), vm))
            if hx:
                return hx
        canvas = vm.get("canvas") or vm.get("paper") or default_bg[theme]
        return _as_hex(_resolve_css_val(canvas, vm)) or default_bg[theme]

    for sel, body in css_rules(text):
        if re.search(r"(^|,)\s*(:root|html)\s*([,{]|$)", sel, re.I) and "--" in body and "color:" not in re.sub(
            r"--[a-z0-9-]+\s*:[^;]+", "", body, flags=re.I
        ):
            continue
        if _is_decoration_color_sel(sel):
            continue
        cm = re.search(r"(?<!-)(?<!outline-)(?<!border-)color\s*:\s*([^;}\n]+)", body, re.I)
        if not cm:
            continue
        # skip custom property definitions accidentally caught
        if re.search(r"--[a-z0-9-]+\s*$", sel, re.I):
            continue
        parts = [p.strip() for p in sel.split(",") if p.strip()]
        # theme from selector
        in_dark = bool(re.search(r"data-theme=['\"]?dark", sel, re.I))
        themes = _rule_themes(sel, in_dark)
        floor = 3.0 if _is_mark_or_large(sel, body) else 4.5
        kind = "mark" if floor == 3.0 else "text"
        for theme in themes:
            vm = maps[theme]
            fg = _as_hex(_resolve_css_val(cm.group(1), vm))
            if not fg or fg not in APPROVED_PINKS:
                continue
            bg = bg_for(body, theme, vm)
            if not bg:
                continue
            if _glass_exception(fg, bg):
                continue
            if floor <= 3.0 and _paper_mark_exception(fg, bg):
                continue
            ratio = contrast_ratio(fg, bg)
            if ratio + 1e-9 < floor:
                issues.append(
                    f"pink-contrast: {sel[:80]} {fg} on {bg} is {ratio:.2f}:1 "
                    f"({kind}, need {floor:.1f}:1) in {theme}"
                )
    seen, uniq = set(), []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def _var_map(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"--([a-z0-9-]+)\s*:\s*([^;}\n]+)", text, re.I)}


def _px(val: str) -> str | None:
    val = val.strip()
    m = re.match(r"(-?[\d.]+)px$", val)
    return m.group(0) if m else None


def _css_width(val: str) -> str | None:
    """Token or declared width: px, or 100% for the phone column."""
    val = val.strip().lower()
    if val in {"100%", "100.00%"} or val.startswith("100%"):
        return "100%"
    return _px(val)


def check_column(css: str) -> list[str]:
    """Require v2 column: 100% (16px side pad) / 720px (24px pad from 768) / 760px from 1024."""
    issues: list[str] = []
    vs = _var_map(css)
    def resolved(val: str) -> str:
        val = val.strip()
        m = re.match(r"var\(--([a-z0-9-]+)(?:,([^)]+))?\)", val, re.I)
        if m:
            name, fallback = m.group(1), m.group(2)
            if name in vs:
                return resolved(vs[name])
            if fallback:
                return resolved(fallback)
        return val

    def as_width(raw: str) -> str | None:
        return _css_width(resolved(_clean_decl(raw)))

    widths: set[str] = set()
    pads: set[str] = set()
    if vs.get("col-s") and vs.get("col-m") and vs.get("col-l"):
        for key in ("col-s", "col-m", "col-l"):
            r = as_width(vs[key])
            if r:
                widths.add(r)
    # main { max-width: ... } including media queries; also side padding
    for sel, body in css_rules(css):
        parts = [p.strip() for p in sel.split(",") if p.strip()]
        if not any(re.search(r"(^|[^a-z-])main$", _subject(p), re.I) or _subject(p) in {"main"} for p in parts):
            # also catch `main` exactly
            if not any(re.search(r"(^|,)\s*main\s*$", p, re.I) for p in parts):
                continue
        m = re.search(r"max-width\s*:\s*([^;}\n]+)", body, re.I)
        if m:
            r = as_width(m.group(1))
            if r:
                widths.add(r)
        # shorthand padding: top right bottom left, or top/bottom + sides
        pm = re.search(r"(?<!-)padding\s*:\s*([^;}\n]+)", body, re.I)
        if pm:
            parts_p = _clean_decl(pm.group(1)).split()
            # 1 value: all sides; 2: block inline; 3: top inline bottom; 4: top right bottom left
            if len(parts_p) == 1:
                side = parts_p[0]
            elif len(parts_p) in (2, 3):
                side = parts_p[1]
            else:
                side = parts_p[1]  # right; left is parts_p[3] — require both later
            r = _css_width(resolved(_clean_decl(side)))
            if r:
                pads.add(r)
            if len(parts_p) == 4:
                r2 = _css_width(resolved(_clean_decl(parts_p[3])))
                if r2:
                    pads.add(r2)
        for prop in ("padding-left", "padding-right", "padding-inline", "padding-inline-start", "padding-inline-end"):
            pm = re.search(rf"{prop}\s*:\s*([^;}}\n]+)", body, re.I)
            if pm:
                r = _css_width(resolved(_clean_decl(pm.group(1))))
                if r:
                    pads.add(r)
    # --col used as the only column (v1)
    if "col" in vs and "col-s" not in vs:
        r = as_width(vs["col"])
        if r:
            widths.add(r)

    need = {"100%", "720px", "760px"}
    if not need.issubset(widths):
        issues.append(f"column: need 100%/720/760px, found {sorted(widths) or 'none'}")
    # Live SÁBÁT: 16px sides on phones, 24px from 768px. Flag if main padding is present but those two are missing.
    if pads and not {"16px", "24px"}.issubset(pads):
        issues.append(f"column padding: need 16px and 24px sides, found {sorted(pads)}")
    return issues


def _font_size_in(body: str) -> list[str]:
    out = []
    for m in re.finditer(r"font-size\s*:\s*([^;}\n]+)", body, re.I):
        val = _clean_decl(m.group(1))
        # max(12px,13px) → treat as 13px if that's the computed max
        mm = re.search(r"max\(\s*[\d.]+px\s*,\s*([\d.]+px)\s*\)", val, re.I)
        if mm:
            out.append(mm.group(1).lower())
            continue
        px = _px(val)
        if px:
            out.append(px.lower())
    return out


def check_type(css: str) -> list[str]:
    """Require Jost scale: h1/.name 24/31, section h2 23, label/caption 13. Fail v1 40/30."""
    issues: list[str] = []
    sizes_h1: set[str] = set()
    sizes_h2: set[str] = set()
    sizes_label: set[str] = set()
    for sel, body in css_rules(css):
        sizes = _font_size_in(body)
        if not sizes:
            continue
        for part in (p.strip() for p in sel.split(",") if p.strip()):
            last = _subject(part)
            if re.search(r"(^|\.)(name|hero h1)$", last, re.I) or last.lower() == "h1" or re.search(r"(^|\.)name$", last, re.I):
                sizes_h1.update(sizes)
            elif last.lower() == "h2" or re.search(r"(^|\.)(sec)$", last, re.I):
                # not .panel h2 specifically required at 15; 23 is the section size
                if not re.search(r"\.panel\s+h2", part, re.I):
                    sizes_h2.update(sizes)
            elif re.search(r"(^|\.)(label|cap)$", last, re.I) or last.lower() in {"figcaption", ".label"}:
                sizes_label.update(sizes)
            elif "figcaption" in last.lower():
                sizes_label.update(sizes)

    if "40px" in sizes_h1 or "30px" in sizes_h1:
        issues.append(f"type: v1 title size {sorted(sizes_h1)}")
    if "12px" in sizes_label and "13px" not in sizes_label:
        issues.append(f"type: v1 caption 12px {sorted(sizes_label)}")
    missing = []
    if not {"24px", "31px"}.issubset(sizes_h1):
        missing.append(f"h1/name 24/31 (found {sorted(sizes_h1) or 'none'})")
    if "23px" not in sizes_h2:
        missing.append(f"h2 23 (found {sorted(sizes_h2) or 'none'})")
    if "13px" not in sizes_label:
        missing.append(f"label/caption 13 (found {sorted(sizes_label) or 'none'})")
    if missing:
        issues.append("type: missing " + "; ".join(missing))
    return issues


def _consume_brace(text: str, open_idx: int) -> str:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
    return text[open_idx + 1 :]


DARK_MARKER = re.compile(
    r"(\[data-theme\s*=\s*['\"]?dark['\"]?\]|\.dark\b|@media\s*\([^)]*prefers-color-scheme\s*:\s*dark[^)]*\))",
    re.I,
)
# --name title (24px+). Accept only mauve. Greys / on-dark fail.
NAME_TITLE_OK = {"#856a8e", "var(--mauve-em)", "var(--mauve-em,#856a8e)", "var(--name)"}
NAME_TITLE_OK.discard("")  # keep a set literal mutable-friendly


def _norm_css_val(val: str) -> str:
    return re.sub(r"\s+", "", _clean_decl(val)).lower()


def _is_name_title_sel(part: str) -> bool:
    """h1 / .name (24px+ title), not h2 or the pink first letter."""
    if re.search(r"(^|[\s>+~])(h2|h3)\b", part, re.I):
        return False
    last = _subject(part)
    if re.search(r"(^|\.)(dc|first)$", last, re.I):
        return False
    if last.lower() == "h1" or re.search(r"(^|\.)name$", last, re.I):
        return True
    if re.search(r"(h1|\.name)\s+\.fa\b", part, re.I):
        return True
    return False


def check_dark_title(css: str) -> list[str]:
    """In dark mode, --name (h1/.name at 24px+) is #856a8e. Do not apply to h2/23px."""
    issues: list[str] = []
    text = _strip_css_comments(css)
    last_name: str | None = None
    bad_colors: list[str] = []
    for m in DARK_MARKER.finditer(text):
        brace = text.find("{", m.end())
        if brace < 0:
            continue
        # skip if this { belongs to a much later rule (no - if there's a } before { that's wrong)
        between = text[m.end() : brace]
        if "}" in between:
            continue
        prefix = text[m.start() : brace].strip()
        inner = _consume_brace(text, brace)
        slice_css = prefix + "{" + inner + "}"
        for mm in re.finditer(r"--name\s*:\s*([^;}\n]+)", slice_css, re.I):
            last_name = mm.group(1).strip()
        for sel, body in css_rules(slice_css):
            if "color" not in body.lower():
                continue
            cm = re.search(r"(?<!-)color\s*:\s*([^;}\n]+)", body, re.I)
            if not cm:
                continue
            val = cm.group(1).strip()
            for part in (p.strip() for p in sel.split(",") if p.strip()):
                if not _is_name_title_sel(part):
                    continue
                nv = _norm_css_val(val)
                if nv in {_norm_css_val(x) for x in ("#856a8e", "var(--mauve-em)", "var(--mauve-em, #856a8e)", "var(--name)")}:
                    continue
                bad_colors.append(f"{part[:60]} color:{_clean_decl(val)}")

    if last_name is None:
        issues.append("dark-title: missing --name #856a8e for 24px+ titles in dark mode")
    elif _norm_css_val(last_name) not in {_norm_css_val(x) for x in ("#856a8e", "var(--mauve-em)", "var(--mauve-em, #856a8e)")}:
        issues.append(f"dark-title: --name is {last_name} (need #856a8e / var(--mauve-em) on 24px+ titles, not grey)")
    for b in bad_colors:
        issues.append(f"dark-title: {b} (24px+ title rest must be #856a8e; h2 unchanged)")
    return issues


def _mask_dark_blocks(text: str) -> str:
    out = list(text)
    for m in DARK_MARKER.finditer(text):
        brace = text.find("{", m.end())
        if brace < 0 or "}" in text[m.end() : brace]:
            continue
        inner = _consume_brace(text, brace)
        end = brace + 1 + len(inner)
        for i in range(m.start(), min(end + 1, len(out))):
            out[i] = " "
    return "".join(out)


def _vars_in(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"--([a-z0-9-]+)\s*:\s*([^;}\n]+)", text, re.I)}


def _theme_vars(css: str) -> tuple[dict[str, str], dict[str, str]]:
    text = _strip_css_comments(css)
    light = _vars_in(_mask_dark_blocks(text))
    dark = dict(light)
    for m in DARK_MARKER.finditer(text):
        brace = text.find("{", m.end())
        if brace < 0 or "}" in text[m.end() : brace]:
            continue
        dark.update(_vars_in(_consume_brace(text, brace)))
    return light, dark


def _resolve_css_val(val: str, vm: dict[str, str], depth: int = 0) -> str:
    val = _clean_decl(val)
    if depth > 8:
        return val
    m = re.match(r"var\(\s*--([a-z0-9-]+)\s*(?:,([^)]+))?\)", val, re.I)
    if not m:
        return val
    name, fallback = m.group(1), m.group(2)
    if name in vm:
        return _resolve_css_val(vm[name], vm, depth + 1)
    if fallback:
        return _resolve_css_val(fallback, vm, depth + 1)
    return val


def _is_exact_pink(val: str, vm: dict[str, str]) -> bool:
    resolved = _norm_css_val(_resolve_css_val(val, vm))
    if resolved in APPROVED_PINKS:
        return True
    if re.fullmatch(r"var\(--(?:pink|pink-mark-light|pink-mark-dark|pink-fill-dark)\)", resolved):
        return True
    if _norm_css_val(val) in APPROVED_PINKS:
        return True
    return False


def _is_whole_heading_sel(part: str) -> bool:
    """h1-h6 as the element, not a first-letter span or ::first-letter."""
    if re.search(r"::first-letter", part, re.I):
        return False
    last = _subject(part)
    if re.search(r"(^|\.)(dc|first)$", last, re.I):
        return False
    return bool(re.match(r"^h[1-6]$", last, re.I))


def _rule_themes(sel: str, in_dark: bool) -> list[str]:
    compact = re.sub(r"\s+", "", sel)
    if re.search(r"data-theme=['\"]?light", sel, re.I) or "not([data-theme=dark])" in compact:
        return ["light"]
    if in_dark or re.search(r"data-theme=['\"]?dark", sel, re.I):
        return ["dark"]
    return ["light", "dark"]


def check_pink_headings(css: str) -> list[str]:
    """FAIL when an h1-h6's whole text is an approved pink. First letter may be pink."""
    issues: list[str] = []
    text = _strip_css_comments(css)
    light, dark = _theme_vars(text)
    maps = {"light": light, "dark": dark}

    def walk(sel: str, body: str, in_dark: bool) -> None:
        cm = re.search(r"(?<!-)color\s*:\s*([^;}\n]+)", body, re.I)
        if not cm:
            return
        val = cm.group(1).strip()
        headings = [p.strip() for p in sel.split(",") if p.strip() and _is_whole_heading_sel(p)]
        if not headings:
            return
        for theme in _rule_themes(sel, in_dark):
            if _is_exact_pink(val, maps[theme]):
                issues.append(
                    f"pink-heading: {', '.join(headings)[:80]} color:{_clean_decl(val)} in {theme} "
                    f"(only the first letter may be pink)"
                )
                return

    for sel, body in css_rules(text):
        walk(sel, body, in_dark=bool(re.search(r"data-theme=['\"]?dark", sel, re.I)))
    for m in DARK_MARKER.finditer(text):
        brace = text.find("{", m.end())
        if brace < 0 or "}" in text[m.end() : brace]:
            continue
        prefix = text[m.start() : brace].strip()
        inner = _consume_brace(text, brace)
        for sel, body in css_rules(prefix + "{" + inner + "}"):
            walk(sel, body, in_dark=True)
    seen, uniq = set(), []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def collect_first_page_css(root: Path) -> str:
    blobs: list[str] = []
    seen: set[Path] = set()

    def add_file(p: Path) -> None:
        try:
            rp = p.resolve()
        except Exception:
            return
        if rp in seen or not p.exists() or not p.is_file():
            return
        seen.add(rp)
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        blobs.append(text)
        for m in re.finditer(r"@import\s+(?:url\()?['\"]([^'\"]+)['\"]", text):
            href = m.group(1).split("?")[0]
            if href.startswith(("http://", "https://", "data:", "//")):
                continue
            if "tailwind" in href:
                continue
            add_file(p.parent / href)

    for rel in ("site/index.html", "index.html", "public/index.html"):
        p = root / rel
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        blobs.append(text)
        for m in re.finditer(r"<link\b[^>]*>", text, re.I):
            tag = m.group(0)
            hm = re.search(r"href=['\"]([^'\"]+)['\"]", tag, re.I)
            if not hm:
                continue
            href = hm.group(1).split("?")[0]
            if href.startswith(("http://", "https://", "data:", "//")):
                continue
            if "stylesheet" not in tag.lower() and not href.endswith(".css"):
                continue
            add_file(p.parent / href)

    extras = [
        root / "site" / "tokens.css",
        root / "tokens.css",
        root / "public" / "design" / "tokens.css",
        root / "src" / "tokens-first-page.css",
        root / "src" / "tokens.css",
        root / "site" / "pages-shell.css",
        root / "pages-shell.css",
        root / "public" / "design" / "pages-shell.css",
        root / "src" / "styles.css",
        root / "src" / "fonts.css",
    ]
    for p in extras:
        if p.exists():
            add_file(p)
    return "\n".join(blobs)


def scan_svg(path: Path, rel: str, palette_only: bool = False):
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []
    if re.search(r"<text\b", text, re.I):
        issues.append("svg-text")
    if not palette_only:
        for hx in check_source_hex(text):
            issues.append("svg-hex:" + hx)
        for f in check_fonts(text):
            issues.append("font:" + f)
        for p in check_pink(text, rel):
            issues.append("pink:" + p)
    # radius is never checked in SVG art
    for hx in check_blue_hex(text):
        issues.append("svg-blue:" + hx)
    blue = 0
    for m in re.finditer(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)", text):
        try:
            raw = base64.b64decode(m.group(2))
            blue += scan_blue_pixels(Image.open(io.BytesIO(raw)))
        except Exception as e:
            issues.append("embed-err:" + str(e)[:60])
    return blue, issues


IMG_TAG = re.compile(r"<img\b[^>]*>", re.I | re.S)
PICTURE_BLOCK = re.compile(r"<picture\b[^>]*>.*?</picture>", re.I | re.S)
SRC_ATTR = re.compile(r"""(?:src|srcset)\s*=\s*['"]([^'"]+)['"]""", re.I)
SKIP_IMG = re.compile(
    r"(favicon|apple-touch-icon|icon-192|icon-512|site\.webmanifest|/icons/)",
    re.I,
)
# DESIGNER photo allowlist: these stay as a single source (no dark variant).
# They are exempt from the no-dark-source rule only; the blue check still runs.
PHOTO_NO_DARK = re.compile(
    r"(?:^|/)(?:disagreement\.svg|fact-vs-taste\.svg|sabat-pavilion\.jpe?g)(?:\?|$)",
    re.I,
)
DARK_SOURCE = re.compile(
    r"<source\b[^>]*(?:media=['\"][^'\"]*prefers-color-scheme\s*:\s*dark|srcset=['\"][^'\"]*[-_]dark\b|src=['\"][^'\"]*[-_]dark\b)",
    re.I,
)


def _img_src(tag: str) -> str:
    m = re.search(r"""src\s*=\s*['"]([^'"]+)['"]""", tag, re.I)
    return m.group(1) if m else "(no src)"


def _skip_content_img(tag: str) -> bool:
    src = _img_src(tag)
    if PHOTO_NO_DARK.search(src):
        return True
    return bool(SKIP_IMG.search(src) or SKIP_IMG.search(tag))


def check_content_images(html: str) -> list[str]:
    """FAIL content <img> with no dark source in a <picture>."""
    issues: list[str] = []
    text = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    covered: list[tuple[int, int]] = []
    for pic in PICTURE_BLOCK.finditer(text):
        block = pic.group(0)
        covered.append((pic.start(), pic.end()))
        img = IMG_TAG.search(block)
        src = _img_src(img.group(0)) if img else "(picture)"
        if img and _skip_content_img(img.group(0)):
            continue
        if not DARK_SOURCE.search(block):
            issues.append(f"picture has no dark source: {src}")
    def in_picture(pos: int) -> bool:
        return any(a <= pos < b for a, b in covered)
    for m in IMG_TAG.finditer(text):
        if in_picture(m.start()):
            continue
        tag = m.group(0)
        if _skip_content_img(tag):
            continue
        issues.append(f"content img has no dark source: {_img_src(tag)}")
    return issues


def run_broken_samples() -> list[str]:
    """Prove contrast, off-palette and alpha rules; approved tokens may be used anywhere.
    Also: square frame FAIL, 12px frame PASS, wrong font FAIL, Jost PASS,
    SVG art radius is ignored."""
    fails: list[str] = []
    body = "p.copy { color: #fcb4c4; } /* body text on paper, 1.61:1 */\n"
    bg = ".panel { background: #fcb4c4; } /* approved fill */\n"
    border = "button.cta { border-color: #fcb4c4; }\n"
    fill_pending = "button.sign { background: #745a7a; }\n"
    tint = ".x { color: #ffb3c3; } /* pink tint */\n"
    tint2 = ".x { color: #ffbfd0; }\n"
    alpha = ".x { color: #fcb4c480; }\n"
    alpha2 = ".x { color: #b7859780; }\n"
    ok_light = ":root:not([data-theme=dark]) .name .first { color: #b78597; background: #f9fafb; }\n"
    ok_dark = "[data-theme=dark] .name .first { color: #fcb4c4; background: #2a272d; }\n"
    glass = ".name .first { color: #b78597; background: #b8adb1; font-size: 31px; }\n"

    def hit(label, src, expect_fail: bool, finder):
        found = finder(src)
        ok_pass = (len(found) > 0) if expect_fail else (len(found) == 0)
        if not ok_pass:
            fails.append(f"BROKEN_SAMPLE {label}: expected_fail={expect_fail} got={found}")
        else:
            print(f"broken-sample {label}: ok (fail={expect_fail}, hits={len(found)})")

    def pink_or_hex(src):
        return check_pink(src, "broken/x.css") + [
            x for x in check_source_hex(src) if "pink" in x or x.startswith("#")
        ]

    hit("body", body, True, lambda s: check_pink_contrast(s) or pink_or_hex(s))
    hit("background", bg, False, pink_or_hex)
    hit("border-ui", border, False, pink_or_hex)
    hit("fill-745a7a", fill_pending, False, pink_or_hex)
    hit("tint", tint, True, check_source_hex)
    hit("tint-ffbfd0", tint2, True, check_source_hex)
    hit("alpha", alpha, True, check_source_hex)
    hit("alpha-b78597", alpha2, True, check_source_hex)
    hit("first-letter-light", ok_light, False, lambda s: check_pink(s, "broken/x.css") + check_pink_contrast(s))
    hit("first-letter-dark", ok_dark, False, lambda s: check_pink(s, "broken/x.css") + check_pink_contrast(s))
    hit("glass-b78597", glass, True, check_pink_contrast)

    # New v2 samples
    hit("square-frame", ".frame { border-radius: 0; }\n", True, check_radius)
    hit("square-panel", ".panel, .card { border-radius: 0px; }\n", True, check_radius)
    hit("rounded-frame", ".frame { border-radius: 12px; }\n", False, check_radius)
    hit("rounded-var", ".panel { border-radius: var(--r-frame); }\n", False, check_radius)
    hit(
        "inner-art-radius-ignored",
        ".frame > img { border-radius: 0; }\nfigure svg { border-radius: 8px; }\n",
        False,
        check_radius,
    )
    hit("wrong-font", "body { font-family: Nunito Sans, system-ui, sans-serif; }\n", True, check_fonts)
    hit("jost-safe", "body { font-family: Jost, sans-serif; }\n", False, check_fonts)
    hit("system-ui", "body { font-family: Jost, system-ui, sans-serif; }\n", True, check_fonts)

    # SVG art radius must not be inspected (no CSS frame selector)
    svg = '<svg><rect x="0" y="0" width="10" height="10" rx="0" ry="0"/></svg>'
    hit("svg-art-square", svg, False, check_radius)
    svg2 = '<svg><rect x="0" y="0" width="10" height="10" rx="12" ry="12"/></svg>'
    hit("svg-art-rounded", svg2, False, check_radius)

    # Column / type positive and negative
    v2col = ":root{--col-s:100%;--col-m:720px;--col-l:760px} main{max-width:var(--col-s);padding:24px 16px 40px} @media (min-width:768px){main{max-width:var(--col-m);padding:40px 24px 56px}} @media (min-width:1024px){main{max-width:var(--col-l)}}"
    hit("column-v2", v2col, False, check_column)
    hit("column-old-448", ":root{--col-s:448px;--col-m:576px;--col-l:672px} main{max-width:var(--col-s)}", True, check_column)
    hit("column-v1", ":root{--col:960px} main{max-width:var(--col)}", True, check_column)
    v2type = "h1,.name{font-size:24px} @media (min-width:768px){h1,.name{font-size:31px}} h2{font-size:23px} .label,figcaption{font-size:13px}"
    hit("type-v2", v2type, False, check_type)
    hit("type-v1", ".name{font-size:40px} @media (max-width:600px){.name{font-size:30px}} figcaption{font-size:12px} h2{font-size:23px}", True, check_type)

    # Control shadow allowed; frame drop shadow fails
    hit(
        "control-shadow-ok",
        "button,.glass{box-shadow:-3px -3px 8px var(--sh-l),4px 4px 10px var(--sh-d),inset 0 1px 0 var(--glass-edge)}",
        False,
        check_frame_shadows,
    )
    hit("frame-shadow-fail", ".frame{box-shadow:0 10px 18px rgba(71,52,72,.1)}", True, check_frame_shadows)
    hit("frame-shadow-none", ".frame{box-shadow:none}", False, check_frame_shadows)

    hit("token-brandon", ':root{--font:"Brandon Text",Jost,system-ui,sans-serif}', True, check_fonts)
    hit("token-jost", ":root{--font:Jost,sans-serif;--font-fa:Vazirmatn,Jost,sans-serif}", False, check_fonts)
    hit("drop-cap-dc", ":root:not([data-theme=dark]) h1 .dc{color:#b78597;background:#f9fafb}", False, lambda s: check_pink(s, "broken/dc.css") + check_pink_contrast(s))
    hit("pink-token-def", ":root{--dc:#fcb4c4;--name:#473448}", False, lambda s: check_pink(s, "broken/tok.css"))

    hit(
        "dark-name-ok",
        "[data-theme=dark]{--name:var(--mauve-em)} h1,.name{color:var(--name)}",
        False,
        check_dark_title,
    )
    hit(
        "dark-name-hex-ok",
        "@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--name:#856a8e}}",
        False,
        check_dark_title,
    )
    hit("dark-name-grey", "[data-theme=dark]{--name:#d4d2d2}", True, check_dark_title)
    hit("dark-name-on-dark", "[data-theme=dark]{--name:var(--on-dark)}", True, check_dark_title)
    hit("dark-h1-grey", "[data-theme=dark]{--name:var(--mauve-em)} [data-theme=dark] h1{color:#d4d2d2}", True, check_dark_title)
    # h2 / 23px headings must not be forced to #856a8e
    hit(
        "dark-h2-untouched",
        "[data-theme=dark]{--name:var(--mauve-em);--sec:var(--pink)} [data-theme=dark] h2{color:#fcb4c4} h2{font-size:23px;color:var(--sec)}",
        False,
        check_dark_title,
    )
    hit(
        "dark-h2-grey-ok",
        "[data-theme=dark]{--name:#856a8e} [data-theme=dark] h2{color:#d4d2d2}",
        False,
        check_dark_title,
    )
    hit("dark-name-missing", "h1,.name{color:var(--name)} :root{--name:var(--plum)}", True, check_dark_title)

    hit("pink-h2-whole", "h2 { color: #fcb4c4; }", True, check_pink_headings)
    hit("pink-h1-whole", ":root{--pink:#fcb4c4} h1{color:var(--pink)}", True, check_pink_headings)
    hit(
        "pink-h2-first-letter",
        "h2::first-letter, h2 .first, h2 .dc { color: #fcb4c4; }",
        False,
        check_pink_headings,
    )
    hit(
        "pink-h2-via-sec-dark",
        "[data-theme=dark]{--sec:var(--pink);--pink:#fcb4c4} h2{color:var(--sec)}",
        True,
        check_pink_headings,
    )
    hit(
        "h2-grey-soft-dark",
        ":root{--sec:#7d5a7c;--grey-soft:#a6a1a7} [data-theme=dark]{--sec:var(--grey-soft)} h2{color:var(--sec)}",
        False,
        check_pink_headings,
    )
    hit(
        "img-no-dark",
        '<img src="hero-light.svg" alt="hero">',
        True,
        check_content_images,
    )
    hit(
        "img-photo-pavilion",
        '<img src="sabat-pavilion.jpg" alt="pavilion">',
        False,
        check_content_images,
    )
    hit(
        "img-photo-disagreement",
        '<img src="../assets/disagreement.svg" alt="board">',
        False,
        check_content_images,
    )
    hit(
        "img-photo-fact-vs-taste",
        '<img src="assets/fact-vs-taste.svg" alt="trays">',
        False,
        check_content_images,
    )
    hit(
        "img-picture-dark",
        '<picture><source media="(prefers-color-scheme: dark)" srcset="hero-dark.svg"><img src="hero-light.svg" alt="hero"></picture>',
        False,
        check_content_images,
    )
    hit(
        "img-picture-light-only",
        '<picture><source media="(prefers-color-scheme: light)" srcset="hero-light.svg"><img src="hero-light.svg" alt="hero"></picture>',
        True,
        check_content_images,
    )
    hit(
        "img-favicon-skip",
        '<img src="/favicon.svg" alt="">',
        False,
        check_content_images,
    )
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--self-test", action="store_true", help="run broken samples and exit")
    args = ap.parse_args()

    if args.self_test:
        fails = run_broken_samples()
        for f in fails:
            print(f)
        print(f"self-test failures={len(fails)}")
        return 1 if fails else 0

    full, palette = load_allowlist()
    failures: list[str] = []
    for p in iter_files():
        rel = p.relative_to(ROOT).as_posix()
        suf = p.suffix.lower()

        if suf in TEXT_EXT:
            if not is_full_allowlisted(p, full):
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    failures.append(f"ERROR {rel}: {e}")
                    continue
                if suf != ".svg":
                    for f in check_fonts(text):
                        failures.append(f"FONT {rel}: {f}")
                    for w in check_weights(text):
                        failures.append(f"WEIGHT {rel}: {w}")
                    for r in check_radius(text):
                        failures.append(f"RADIUS {rel}: {r}")
                    for sh in check_frame_shadows(text):
                        failures.append(f"SHADOW {rel}: {sh}")
                    for hx in check_source_hex(text):
                        if hx.startswith("pink-"):
                            failures.append(f"PINK {rel}: {hx}")
                        else:
                            failures.append(f"HEX {rel}: {hx}")
                    for pk in check_pink(text, rel):
                        failures.append(f"PINK {rel}: {pk}")
                    if suf in {".css", ".html"}:
                        for iss in check_pink_headings(text):
                            failures.append(f"PINK_HEADING {rel}: {iss}")
                        for iss in check_pink_contrast(text):
                            failures.append(f"PINK_CONTRAST {rel}: {iss}")
                    if suf == ".html":
                        for iss in check_content_images(text):
                            failures.append(f"IMAGE {rel}: {iss}")

        if suf not in IMG_EXT:
            continue
        if is_full_allowlisted(p, full):
            continue
        pal = is_palette_only(p, palette)
        try:
            if suf == ".svg":
                blue, issues = scan_svg(p, rel, palette_only=pal)
                if "svg-text" in issues:
                    failures.append(f"SVG_TEXT {rel}: unoutlined <text>")
                for iss in issues:
                    if iss.startswith("svg-hex:"):
                        val = iss.split(":", 1)[1]
                        if val.startswith("pink-"):
                            failures.append(f"PINK {rel}: {val}")
                        else:
                            failures.append(f"HEX {rel}: {val}")
                    elif iss.startswith("svg-blue:"):
                        failures.append(f"BLUE {rel}: hex {iss.split(':', 1)[1]}")
                    elif iss.startswith("font:"):
                        failures.append(f"FONT {rel}: {iss.split(':', 1)[1]}")
                    elif iss.startswith("pink:"):
                        failures.append(f"PINK {rel}: {iss.split(':', 1)[1]}")
                if blue > 12:
                    failures.append(f"BLUE {rel}: ~{blue} blue samples")
            else:
                blue = scan_blue_pixels(Image.open(p))
                if blue > 12:
                    failures.append(f"BLUE {rel}: ~{blue} blue samples")
        except Exception as e:
            failures.append(f"ERROR {rel}: {e}")

    page_css = collect_first_page_css(ROOT)
    if page_css.strip():
        for iss in check_column(page_css):
            failures.append(f"COLUMN {iss}")
        for iss in check_type(page_css):
            failures.append(f"TYPE {iss}")
        for iss in check_dark_title(page_css):
            failures.append(f"DARK_TITLE {iss}")
        for iss in check_pink_headings(page_css):
            failures.append(f"PINK_HEADING {iss}")
        for iss in check_pink_contrast(page_css):
            failures.append(f"PINK_CONTRAST {iss}")

    seen = set()
    uniq = []
    for f in failures:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    failures = uniq

    print(f"allowed_hex={sorted(ALLOWED_HEX)}")
    print(f"allowlist={len(full)} palette_only={len(palette)} failures={len(failures)}")
    for f in failures:
        print(f)
    if args.report:
        args.report.write_text("\n".join(failures) + ("\n" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
