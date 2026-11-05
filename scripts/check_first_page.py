#!/usr/bin/env python3
"""First-page CI: palette, fonts, blue pixels, unoutlined SVG text."""
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
SKIP_DIRS = {".git", "node_modules", "dist", "vendor", "__pycache__", ".venv", "pr-shots"}

FALLBACK_HEX = {
    "#f9fafb", "#5a515c", "#473448", "#856a8e", "#7d5a7c", "#775a76",
    "#948e95", "#a6a1a7", "#fcb4c4", "#2a272d", "#d4d2d2",
}

ALLOWED_FONT_OK = re.compile(
    r"^(jost|vazirmatn|brandon text|system-ui|sans-serif|serif|monospace|"
    r"ui-monospace|menlo|sfmono-regular|inherit|emoji|apple color emoji|"
    r"segoe ui emoji|arial|helvetica|helvetica neue|avenir|avenir next|"
    r"var\(|noto naskh arabic|noto sans arabic)$",
    re.I,
)
BAD_FONT = re.compile(
    r"nunito|inter|roboto|open sans|montserrat|poppins|lato|raleway|"
    r"source sans|pt sans|ubuntu|fira|georgia|times new roman|comic sans",
    re.I,
)


def load_allowed_hex() -> set[str]:
    for p in TOKENS_CANDIDATES:
        if p.exists():
            return set(
                h.lower()
                for h in re.findall(r"#[0-9A-Fa-f]{6}\b", p.read_text(encoding="utf-8", errors="ignore"))
            )
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
        if rel.startswith(a.rstrip("/") + "/") or rel == a:
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


def scan_rgba(im: Image.Image, max_px: int = 2_000_000):
    im = im.convert("RGBA")
    w, h = im.size
    if w * h > max_px:
        scale = (max_px / (w * h)) ** 0.5
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    px = im.getdata()
    blue = off = 0
    samples: set[str] = set()
    step = max(1, len(px) // 200_000)
    for i in range(0, len(px), step):
        r, g, b, a = px[i]
        if a < 16:
            continue
        hue, sat, val = rgb_to_hue_sat(r, g, b)
        if 190 <= hue <= 250 and sat > 0.25 and val > 0.12:
            blue += 1
        if not near_allowed(r, g, b):
            off += 1
            if len(samples) < 8:
                samples.add("#{:02x}{:02x}{:02x}".format(r, g, b))
    return blue, off, samples


def scan_svg(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []
    if re.search(r"<text\b", text, re.I):
        issues.append("svg-text")
    check = re.sub(r"data:image/[^\"']+", "", text)
    for h in re.findall(r"#[0-9A-Fa-f]{3,8}\b", check):
        hx = expand(h)
        if len(hx) != 7:
            continue
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        if not near_allowed(r, g, b):
            issues.append("svg-hex:" + hx)
    blue = off = 0
    samples: set[str] = set()
    for m in re.finditer(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)", text):
        try:
            raw = base64.b64decode(m.group(2))
            im = Image.open(io.BytesIO(raw))
            b, o, s = scan_rgba(im)
            blue += b
            off += o
            samples |= s
        except Exception as e:
            issues.append("embed-err:" + str(e)[:60])
    return blue, off, samples, issues


FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.I)


def check_css_fonts(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    bad: list[str] = []
    for m in FONT_FAMILY_RE.finditer(text):
        for n in (x.strip().strip("'\"") for x in m.group(1).split(",")):
            if not n or n.startswith("var("):
                continue
            if ALLOWED_FONT_OK.match(n) or ALLOWED_FONT_OK.match(n.split()[0]):
                continue
            if BAD_FONT.search(n):
                bad.append(n)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()
    allow = load_allowlist()
    failures: list[str] = []
    for p in iter_files():
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix.lower() in {".css", ".html", ".js", ".tsx", ".ts", ".mjs", ".svg"}:
            if not is_allowlisted(p, allow) and p.suffix.lower() != ".svg":
                bad = check_css_fonts(p)
                if bad:
                    failures.append(f"FONT {rel}: {sorted(set(bad))}")
        if p.suffix.lower() not in IMG_EXT:
            continue
        if is_allowlisted(p, allow):
            continue
        try:
            if p.suffix.lower() == ".svg":
                blue, off, samples, issues = scan_svg(p)
                if "svg-text" in issues:
                    failures.append(f"SVG_TEXT {rel}: unoutlined <text>")
                for iss in issues:
                    if iss.startswith("svg-hex:"):
                        failures.append(f"HEX {rel}: {iss.split(':', 1)[1]}")
                if blue > 12:
                    failures.append(f"BLUE {rel}: ~{blue} blue samples")
                if off > 80:
                    failures.append(f"OFFPALETTE {rel}: ~{off} {sorted(samples)[:6]}")
            else:
                blue, off, samples = scan_rgba(Image.open(p))
                if blue > 12:
                    failures.append(f"BLUE {rel}: ~{blue} blue samples")
                if off > 80:
                    failures.append(f"OFFPALETTE {rel}: ~{off} {sorted(samples)[:6]}")
        except Exception as e:
            failures.append(f"ERROR {rel}: {e}")
    print(f"allowed_hex={sorted(ALLOWED_HEX)}")
    print(f"allowlist={len(allow)} failures={len(failures)}")
    for f in failures:
        print(f)
    if args.report:
        args.report.write_text("\n".join(failures) + ("\n" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
