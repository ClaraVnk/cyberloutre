#!/usr/bin/env python3
"""Generate the OG image for the smart-home page.

Composites the Home Assistant brand logo + page title on a dark gradient
background coherent with the page theme. Output: 1200×630 WebP suitable
for og:image meta.
"""
from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import urllib.request

OUT = Path("/Users/claravanacker/Projects/cyberloutre.fr/static/img/smart-home/og-smart-home.png")
LOGO_URL = "https://brands.home-assistant.io/_/homeassistant/logo.png"
LOGO_TMP = Path("/tmp/ha-logo.png")

W, H = 1200, 630


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths_bold = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    paths_regular = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in (paths_bold if bold else paths_regular):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size, index=1 if bold and p.endswith(".ttc") else 0)
            except Exception:
                continue
    return ImageFont.load_default()


def main():
    if not LOGO_TMP.exists():
        urllib.request.urlretrieve(LOGO_URL, LOGO_TMP)

    # Base : dark gradient navy → near-black
    img = Image.new("RGB", (W, H), (15, 17, 25))
    px = img.load()
    for y in range(H):
        # Subtle vertical gradient
        t = y / H
        r = int(15 + (25 - 15) * t)
        g = int(17 + (29 - 17) * t)
        b = int(25 + (38 - 25) * t)
        for x in range(W):
            px[x, y] = (r, g, b)

    # Radial glow top-right (cyan accent), bottom-left (violet)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    # Cyan glow
    for r, a in [(420, 50), (300, 70), (180, 90)]:
        glow_draw.ellipse([W - 200 - r, -r + 60, W - 200 + r, r + 60],
                           fill=(125, 211, 252, a))
    # Violet glow
    for r, a in [(380, 40), (260, 55), (150, 75)]:
        glow_draw.ellipse([180 - r, H - 80 - r, 180 + r, H - 80 + r],
                           fill=(139, 92, 246, a))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    img.paste(Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB"))

    draw = ImageDraw.Draw(img)

    # HA logo : load, resize, paste top-left
    logo = Image.open(LOGO_TMP).convert("RGBA")
    logo_w = 380
    logo_h = int(logo.height * (logo_w / logo.width))
    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
    img_rgba = img.convert("RGBA")
    img_rgba.paste(logo, (80, 80), logo)
    img = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Main title
    font_title = load_font(86, bold=True)
    title = "Ma maison qui pense."
    draw.text((80, 220), title, font=font_title, fill=(255, 255, 255))

    # Tagline
    font_sub = load_font(32)
    sub_lines = [
        "Architecture Home Assistant — 183 appareils,",
        "122 automatisations, un Pi tactile dans l'entrée.",
    ]
    y = 360
    for line in sub_lines:
        draw.text((80, y), line, font=font_sub, fill=(168, 174, 189))
        y += 44

    # Bottom-right brand
    font_brand = load_font(22)
    brand = "cyberloutre.fr"
    bbox = draw.textbbox((0, 0), brand, font=font_brand)
    bw = bbox[2] - bbox[0]
    draw.text((W - 80 - bw, H - 50), brand, font=font_brand, fill=(125, 211, 252))

    # Subtle bottom-left accent dot
    draw.ellipse([76, H - 56, 92, H - 40], fill=(125, 211, 252))

    img.save(OUT, "PNG", optimize=True)
    print(f"✓ OG saved → {OUT} ({OUT.stat().st_size // 1024} KB, {img.size})")


if __name__ == "__main__":
    main()
