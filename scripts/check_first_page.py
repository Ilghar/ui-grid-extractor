#!/usr/bin/env python3
"""First-page CI: radius 0, no SVG <text>, fonts Jost/Vazirmatn/var(--font*) only,
off-palette #hex in source, blue pixels in rasters/SVG embeds.

Pink #fcb4c4 (exact only) PASS when:
  (a) title first letter (.first / ::first-letter / title-initial),
  (b) the "i" in the ilghar.studio wordmark,
  (c) accents inside illustration SVGs or Persian marks (امتناع).
FAIL: pink tints / near-pink (not exact #fcb4c4), pink with opacity/alpha,
pink in body text, pink in UI chrome (buttons, borders, inputs, nav) or
backgrounds, and any blue.
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import io
import re
import sys
import tempfile
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
    "#948e95", "#a6a1a7", "#fcb4c4", "#2a272d", "#d4d2d2",
}
PINK = "#fcb4c4"
PINK_RGB = (0xFC, 0xB4, 0xC4)

FONT_TOKEN_OK = re.compile(
    r"^(jost|vazirmatn|var\(\s*--font[a-z0-9-]*\s*(\s*,\s*[^)]+)?\))$",
    re.I,
)
RADIUS_ZERO = re.compile(r"^0(px|%)?(\s*!important)?$", re.I)

FONT_FAMILY_CSS = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.I)
FONT_FAMILY_ATTR = re.compile(r"font-family\s*=\s*[\"']([^\"']+)[\"']", re.I)
FONT_SHORTHAND = re.compile(
    r"font\s*:\s*(?:(?:normal|italic|oblique|bold|bolder|lighter|\d{3})\s+)*"
    r"[\d.]+(?:px|rem|em|%)?(?:\s*/\s*[\d.]+(?:px|rem|em|%|))?\s+([^;}\"']+)",
    re.I,
)
BORDER_RADIUS = re.compile(r"border-radius\s*:\s*([^;}\n]+)", re.I)
RECT_RX_RY = re.compile(r"<rect\b[^>]*?\b(rx|ry)\s*=\s*[\"']([^\"']+)[\"']", re.I | re.S)

# PASS contexts for exact #fcb4c4 / var(--pink)
PINK_OK_CONTEXT = re.compile(
    r"("
    r"\.first\b|::first-letter|first-letter|"
    r"title.?initial|pink.?initial|span\.first|h1\s+\.first|"
    r"\.name\s+\.first|\.hero\s+\.first|"
    r"class(?:Name)?=\"[^\"]*\bfirst\b|"
    r"wordmark|\.wm-i\b|\.brand-i\b|ilghar[^\n]{0,40}\.first|"
    r"امتناع|"
    r"--pink\s*:"
    r")",
    re.I,
)

# FAIL even if near an OK cue: body copy, UI chrome, backgrounds
PINK_FAIL_CONTEXT = re.compile(
    r"("
    r"background(?:-color)?\s*:|"
    r"border(?:-color)?\s*:|"
    r"\bbutton\b|\.btn\b|\.button\b|"
    r"\binput\b|\.input\b|\bnav\b|\.nav\b|"
    r"\bbody\b|\.body-text\b|\.prose\b|"
    r"opacity\s*:|color-mix\("
    r")",
    re.I,
)

ILLUSTRATION_SVG = re.compile(
    r"(?:^|/)(?:docs/hero/|assets/)?(?:hero|board|og|illustration|mark)[^/]*\.svg$",
    re.I,
)


def load_allowed_hex() -> set[str]:
    for p in TOKENS_CANDIDATES:
        if p.exists():
            found = set(
                h.lower()
                for h in re.findall(r"#[0-9A-Fa-f]{6}\b", p.read_text(encoding="utf-8", errors="ignore"))
            )
            if found:
                return found
    return set(FALLBACK_HEX)


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
    """Pinkish hue that is not exact #fcb4c4."""
    if (r, g, b) == PINK_RGB:
        return False
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue = h * 360.0
    # pink/rose band
    if s < 0.15 or v < 0.35:
        return False
    return (hue >= 320 or hue <= 20)


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        return set()
    out: set[str] = set()
    for line in ALLOWLIST.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line.replace("\\", "/"))
    return out


def is_allowlisted(path: Path, allow: set[str]) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in allow:
        return True
    for a in allow:
        if a.endswith("/") and rel.startswith(a):
            return True
        if rel == a or rel.startswith(a.rstrip("/") + "/"):
            return True
    return False


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(x in SKIP_DIRS for x in p.parts):
            continue
        yield p


def rgb_to_hue_sat(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s, v


def scan_blue_pixels(im: Image.Image, max_px: int = 2_000_000) -> int:
    im = im.convert("RGBA")
    w, h = im.size
    if w * h > max_px:
        scale = (max_px / (w * h)) ** 0.5
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    px = im.getdata()
    blue = 0
    step = max(1, len(px) // 200_000)
    for i in range(0, len(px), step):
        r, g, b, a = px[i]
        if a < 16:
            continue
        hue, sat, val = rgb_to_hue_sat(r, g, b)
        if 190 <= hue <= 250 and sat > 0.25 and val > 0.12:
            blue += 1
    return blue


def font_parts_ok(family_list: str) -> list[str]:
    bad: list[str] = []
    for n in (x.strip().strip("'\"") for x in family_list.split(",")):
        if not n:
            continue
        if FONT_TOKEN_OK.match(n) or re.match(r"^var\(\s*--font", n, re.I):
            continue
        bad.append(n)
    return bad


def check_fonts(text: str) -> list[str]:
    bad: list[str] = []
    for m in FONT_FAMILY_CSS.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    for m in FONT_FAMILY_ATTR.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    for m in FONT_SHORTHAND.finditer(text):
        bad.extend(font_parts_ok(m.group(1)))
    return bad


def check_radius(text: str, is_svg: bool = True) -> list[str]:
    bad: list[str] = []
    for m in BORDER_RADIUS.finditer(text):
        val = m.group(1).strip()
        if not RADIUS_ZERO.match(val):
            bad.append(f"border-radius:{val}")
    for m in RECT_RX_RY.finditer(text):
        attr, val = m.group(1), m.group(2).strip()
        if val not in {"0", "0px"}:
            bad.append(f"rect {attr}={val}")
    return bad


def check_source_hex(text: str) -> list[str]:
    check = re.sub(r"data:image/[^\"']+", "", text)
    bad: list[str] = []
    for h in set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", check)):
        raw = h.lower()
        # 8-digit / alpha on pink → fail
        if len(raw) == 9 and raw[:7] == PINK:
            bad.append(f"pink-alpha:{raw}")
            continue
        hx = expand(raw)
        if len(hx) != 7:
            continue
        if hx == PINK:
            continue  # owned by check_pink
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        if is_pink_tint(r, g, b):
            bad.append(f"pink-tint:{hx}")
            continue
        if not near_allowed(r, g, b):
            bad.append(hx)
    return bad


def check_pink(text: str, rel: str) -> list[str]:
    """Exact #fcb4c4 / var(--pink) only in allowed accent contexts."""
    issues: list[str] = []
    if rel.endswith("tokens.css") or rel.endswith("tokens-first-page.css"):
        return issues
    # Illustration SVGs may use exact pink accents freely
    if rel.endswith(".svg") and ILLUSTRATION_SVG.search(rel):
        return issues
    # Also allow any svg under docs/hero or assets that looks like board/hero
    if rel.endswith(".svg") and re.search(r"(?:^|/)(?:docs/hero|assets)/(?:hero|board)", rel):
        return issues

    for m in re.finditer(r"#fcb4c4|var\(\s*--pink\s*\)", text, re.I):
        start = max(0, m.start() - 220)
        end = min(len(text), m.end() + 100)
        ctx = text[start:end]
        # Alpha / opacity / color-mix on pink → fail
        if re.search(r"#fcb4c4[0-9a-fA-F]{2}\b", ctx) or re.search(
            r"(opacity\s*:\s*[^;]+|color-mix\([^)]*#fcb4c4|rgba?\(\s*252\s*,\s*180\s*,\s*196\s*,)",
            ctx,
            re.I,
        ):
            issues.append(f"pink-alpha near: {ctx.replace(chr(10), ' ')[:90]!r}")
            continue
        if PINK_FAIL_CONTEXT.search(ctx):
            issues.append(f"pink-ui-or-body near: {ctx.replace(chr(10), ' ')[:90]!r}")
            continue
        if PINK_OK_CONTEXT.search(ctx):
            continue
        if re.search(r"--pink\s*:\s*#fcb4c4", ctx, re.I) or re.search(r"pink\s*:\s*#fcb4c4", ctx, re.I):
            continue
        issues.append(f"pink-not-accent near: {ctx.replace(chr(10), ' ')[:90]!r}")
    return issues


def scan_svg(path: Path, rel: str):
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []
    if re.search(r"<text\b", text, re.I):
        issues.append("svg-text")
    for hx in check_source_hex(text):
        issues.append("svg-hex:" + hx)
    for r in check_radius(text, True):
        issues.append("radius:" + r)
    for f in check_fonts(text):
        issues.append("font:" + f)
    for p in check_pink(text, rel):
        issues.append("pink:" + p)
    blue = 0
    for m in re.finditer(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)", text):
        try:
            raw = base64.b64decode(m.group(2))
            blue += scan_blue_pixels(Image.open(io.BytesIO(raw)))
        except Exception as e:
            issues.append("embed-err:" + str(e)[:60])
    return blue, issues


def run_broken_samples() -> list[str]:
    """Prove body-text pink and background pink both FAIL; first-letter PASS."""
    fails: list[str] = []
    body = "p.copy { color: #fcb4c4; } /* body text */\n"
    bg = ".panel { background: #fcb4c4; } /* background */\n"
    border = "button.cta { border-color: #fcb4c4; }\n"
    tint = ".x { color: #ffb3c3; } /* pink tint */\n"
    alpha = ".x { color: #fcb4c480; }\n"
    ok = ".name .first { color: #fcb4c4; /* title initial */ }\n"

    def hit(label, src, expect_fail: bool):
        found = check_pink(src, f"broken/{label}.css") + [
            x for x in check_source_hex(src) if "pink" in x or x.startswith("#")
        ]
        # For tint/alpha, hex checker carries the signal
        if label in ("tint", "alpha"):
            found = check_source_hex(src)
        ok_pass = (len(found) > 0) if expect_fail else (len(found) == 0)
        if not ok_pass:
            fails.append(f"BROKEN_SAMPLE {label}: expected_fail={expect_fail} got={found}")
        else:
            print(f"broken-sample {label}: ok (fail={expect_fail}, hits={len(found)})")

    hit("body", body, True)
    hit("background", bg, True)
    hit("border-ui", border, True)
    hit("tint", tint, True)
    hit("alpha", alpha, True)
    hit("first-letter", ok, False)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--self-test", action="store_true", help="run broken pink samples and exit")
    args = ap.parse_args()

    if args.self_test:
        fails = run_broken_samples()
        for f in fails:
            print(f)
        print(f"self-test failures={len(fails)}")
        return 1 if fails else 0

    allow = load_allowlist()
    failures: list[str] = []
    for p in iter_files():
        rel = p.relative_to(ROOT).as_posix()
        suf = p.suffix.lower()

        if suf in TEXT_EXT:
            if not is_allowlisted(p, allow):
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    failures.append(f"ERROR {rel}: {e}")
                    continue
                if suf != ".svg":
                    for f in check_fonts(text):
                        failures.append(f"FONT {rel}: {f}")
                    for r in check_radius(text, True):
                        failures.append(f"RADIUS {rel}: {r}")
                    for hx in check_source_hex(text):
                        if hx.startswith("pink-"):
                            failures.append(f"PINK {rel}: {hx}")
                        else:
                            failures.append(f"HEX {rel}: {hx}")
                    for pk in check_pink(text, rel):
                        failures.append(f"PINK {rel}: {pk}")

        if suf not in IMG_EXT:
            continue
        if is_allowlisted(p, allow):
            continue
        try:
            if suf == ".svg":
                blue, issues = scan_svg(p, rel)
                if "svg-text" in issues:
                    failures.append(f"SVG_TEXT {rel}: unoutlined <text>")
                for iss in issues:
                    if iss.startswith("svg-hex:"):
                        val = iss.split(":", 1)[1]
                        if val.startswith("pink-"):
                            failures.append(f"PINK {rel}: {val}")
                        else:
                            failures.append(f"HEX {rel}: {val}")
                    elif iss.startswith("radius:"):
                        failures.append(f"RADIUS {rel}: {iss.split(':', 1)[1]}")
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

    seen = set()
    uniq = []
    for f in failures:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    failures = uniq

    print(f"allowed_hex={sorted(ALLOWED_HEX)}")
    print(f"allowlist={len(allow)} failures={len(failures)}")
    for f in failures:
        print(f)
    if args.report:
        args.report.write_text("\n".join(failures) + ("\n" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
