#!/usr/bin/env python3
"""First-page CI: radius 0, no SVG <text>, fonts Jost/Vazirmatn/var(--font*) only,
off-palette #hex in source, blue pixels in rasters/SVG embeds,
pink #fcb4c4 only on title initials.

Why earlier misses (fixed here):
1. No border-radius / rect rx|ry check at all.
2. Font allowlist permitted system-ui, sans-serif, Arial, monospace, etc.
3. Font scan used only `font-family:` (CSS) and skipped .svg files, so SVG
   `font-family="..."` attributes were never checked.
4. SVG <text> was detected, but CI noise from off-palette *pixel* sampling of
   photos drowned the signal; hex check is now source-#hex only, blue is pixels.
5. Pink #fcb4c4 was unrestricted; now only title-initial contexts are allowed.
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import io
import re
import sys
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

# Title-initial contexts where #fcb4c4 / var(--pink) is allowed
PINK_OK_CONTEXT = re.compile(
    r"(\.first\b|::first-letter|first-letter|--pink\s*:|"
    r"title.?initial|pink.?initial|span\.first|h1\s+\.first|"
    r"\.name\s+\.first|\.hero\s+\.first|"
    r"class(?:Name)?=\"[^\"]*\bfirst\b)",
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
    """Always scan CSS border-radius and any <rect rx|ry> (incl. inline SVG)."""
    bad: list[str] = []
    for m in BORDER_RADIUS.finditer(text):
        val = m.group(1).strip()
        if not RADIUS_ZERO.match(val):
            bad.append(f"border-radius:{val}")
    # is_svg kept for callers; always scan rect attrs (inline SVG in HTML/TSX too)
    for m in RECT_RX_RY.finditer(text):
        attr, val = m.group(1), m.group(2).strip()
        if val not in {"0", "0px"}:
            bad.append(f"rect {attr}={val}")
    return bad


def check_source_hex(text: str) -> list[str]:
    check = re.sub(r"data:image/[^\"']+", "", text)
    bad: list[str] = []
    for h in set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", check)):
        hx = expand(h)
        if len(hx) != 7:
            continue
        if hx == PINK:
            continue  # owned by check_pink_initials
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        if not near_allowed(r, g, b):
            bad.append(hx)
    return bad


def check_pink_initials(text: str, rel: str) -> list[str]:
    """Flag #fcb4c4 / var(--pink) uses that are not title-initial contexts."""
    issues: list[str] = []
    # Token definitions themselves are OK
    if rel.endswith("tokens.css") or rel.endswith("tokens-first-page.css"):
        return issues
    # Title-card heroes + Proto project boards: pink first letter / title initial expected
    if re.search(r"(docs/hero/hero-(light|dark)|(?:^|/)(?:board|hero)-(light|dark))\.svg$", rel):
        return issues
    # Find pink hex occurrences with local context
    for m in re.finditer(r"#fcb4c4|var\(\s*--pink\s*\)", text, re.I):
        start = max(0, m.start() - 200)
        end = min(len(text), m.end() + 80)
        ctx = text[start:end]
        if PINK_OK_CONTEXT.search(ctx):
            continue
        # CSS custom property assignment --pink:#fcb4c4 (allow truncated lookbehind)
        if re.search(r"--pink\s*:\s*#fcb4c4", ctx, re.I) or re.search(r"pink\s*:\s*#fcb4c4", ctx, re.I):
            continue
        issues.append(f"pink-not-initial near: {ctx.replace(chr(10), ' ')[:90]!r}")
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
    for p in check_pink_initials(text, rel):
        issues.append("pink:" + p)
    blue = 0
    for m in re.finditer(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)", text):
        try:
            raw = base64.b64decode(m.group(2))
            blue += scan_blue_pixels(Image.open(io.BytesIO(raw)))
        except Exception as e:
            issues.append("embed-err:" + str(e)[:60])
    return blue, issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()
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
                        failures.append(f"HEX {rel}: {hx}")
                    for pk in check_pink_initials(text, rel):
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
                        failures.append(f"HEX {rel}: {iss.split(':', 1)[1]}")
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
