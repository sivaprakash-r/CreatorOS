"""Poster composition: turns a background image (from the Mesh image model, or a procedural fallback)
into a branded social visual — brand chip, headline, subline — using Pillow.

Text is rendered here, not by the image model: image models render lettering unreliably, and the
headline must match the piece exactly.
"""

from __future__ import annotations

import colorsys
import hashlib
import io
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_NO_GLYPH = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200D]")


def _clean(text: str) -> str:
    """Inter has no emoji glyphs — drop them (and tidy spaces) before typesetting."""
    return re.sub(r"\s{2,}", " ", _NO_GLYPH.sub("", text)).strip()

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT_BOLD = ASSETS / "Inter-Bold.otf"
FONT_REG = ASSETS / "Inter-Regular.otf"

PALETTES = {
    "warm": ((214, 112, 36), (92, 38, 10)),
    "cool": ((38, 86, 214), (12, 20, 60)),
    "forest": ((38, 160, 110), (8, 40, 32)),
    "berry": ((190, 48, 120), (50, 10, 40)),
    "slate": ((90, 100, 130), (18, 20, 30)),
    "amber": ((245, 185, 66), (60, 36, 8)),
}


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:  # pragma: no cover - assets missing
        return ImageFont.load_default(size)


def _palette_for(key: str | None, seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if key in PALETTES:
        return PALETTES[key]
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.45, 0.6)
    r2, g2, b2 = colorsys.hls_to_rgb(h / 360, 0.12, 0.5)
    return (int(r * 255), int(g * 255), int(b * 255)), (int(r2 * 255), int(g2 * 255), int(b2 * 255))


def fallback_background(size: tuple[int, int], palette: str | None, seed: str) -> Image.Image:
    """Procedural gradient with soft orbs — used when the image model is unavailable."""
    w, h = size
    c1, c2 = _palette_for(palette, seed)
    img = Image.new("RGB", size, c2)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        for x in range(w):
            u = x / max(1, w - 1)
            k = (0.65 * t + 0.35 * (1 - u))
            px[x, y] = tuple(int(c1[i] * (1 - k) + c2[i] * k) for i in range(3))
    orbs = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(orbs)
    rnd = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    for i in range(3):
        cx = (rnd >> (i * 8)) % w
        cy = (rnd >> (i * 8 + 4)) % h
        r = int(min(w, h) * (0.25 + 0.12 * i))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*c1, 70))
    orbs = orbs.filter(ImageFilter.GaussianBlur(min(w, h) // 8))
    img.paste(orbs, (0, 0), orbs)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def compose_poster(
    *,
    background: bytes | None,
    size: tuple[int, int],
    brand: str,
    headline: str,
    subline: str = "",
    palette: str | None = None,
    seed: str = "",
) -> bytes:
    w, h = size
    if background:
        try:
            bg = Image.open(io.BytesIO(background)).convert("RGB")
            # cover-fit
            scale = max(w / bg.width, h / bg.height)
            bg = bg.resize((math.ceil(bg.width * scale), math.ceil(bg.height * scale)))
            left, top = (bg.width - w) // 2, (bg.height - h) // 2
            bg = bg.crop((left, top, left + w, top + h))
        except Exception:
            bg = fallback_background(size, palette, seed or headline)
    else:
        bg = fallback_background(size, palette, seed or headline)

    # bottom gradient for legibility
    grad = Image.new("L", (1, h))
    for y in range(h):
        t = y / h
        grad.putpixel((0, y), int(255 * min(1.0, max(0.0, (t - 0.38) / 0.62)) ** 1.4 * 0.88))
    shade = Image.new("RGB", size, (8, 8, 12))
    bg.paste(shade, (0, 0), grad.resize(size))

    draw = ImageDraw.Draw(bg)
    pad = int(w * 0.06)
    unit = min(w, h)

    # brand chip
    chip_font = _font(FONT_BOLD, int(unit * 0.034))
    chip_text = _clean(brand)[:40]
    tw = draw.textlength(chip_text, font=chip_font)
    ch = int(unit * 0.062)
    badge = int(ch * 0.78)
    x0, y0 = pad, pad
    draw.rounded_rectangle((x0, y0, x0 + badge + tw + int(ch * 0.9), y0 + ch), radius=ch // 2, fill=(255, 255, 255, 230))
    initials = "".join(p[0] for p in chip_text.split()[:2]).upper() or "C"
    c1, _ = _palette_for(palette, seed or headline)
    draw.ellipse((x0 + (ch - badge) // 2, y0 + (ch - badge) // 2, x0 + (ch - badge) // 2 + badge, y0 + (ch - badge) // 2 + badge), fill=c1)
    ini_font = _font(FONT_BOLD, int(badge * 0.46))
    draw.text((x0 + ch / 2, y0 + ch / 2), initials, font=ini_font, fill="white", anchor="mm")
    draw.text((x0 + ch + int(ch * 0.15), y0 + ch / 2), chip_text, font=chip_font, fill=(20, 20, 24), anchor="lm")

    # headline + subline (bottom-left)
    max_w = w - 2 * pad
    head_size = int(unit * 0.085)
    head_font = _font(FONT_BOLD, head_size)
    headline, subline = _clean(headline), _clean(subline)
    lines = _wrap(draw, headline, head_font, max_w)
    while len(lines) > 3 and head_size > int(unit * 0.05):
        head_size = int(head_size * 0.9)
        head_font = _font(FONT_BOLD, head_size)
        lines = _wrap(draw, headline, head_font, max_w)
    lines = lines[:3]
    sub_font = _font(FONT_REG, int(unit * 0.036))
    sub_lines = _wrap(draw, subline, sub_font, max_w)[:2] if subline else []

    line_h = int(head_size * 1.12)
    sub_h = int(unit * 0.036 * 1.35)
    block_h = len(lines) * line_h + (len(sub_lines) * sub_h + int(unit * 0.02) if sub_lines else 0)
    y = h - pad - block_h
    for ln in lines:
        draw.text((pad, y), ln, font=head_font, fill="white")
        y += line_h
    if sub_lines:
        y += int(unit * 0.02)
        for ln in sub_lines:
            draw.text((pad, y), ln, font=sub_font, fill=(235, 235, 240))
            y += sub_h

    # accent bar
    draw.rounded_rectangle((pad, h - pad - block_h - int(unit * 0.035), pad + int(unit * 0.09), h - pad - block_h - int(unit * 0.022)), radius=4, fill=c1)

    out = io.BytesIO()
    bg.save(out, format="PNG", optimize=True)
    return out.getvalue()
