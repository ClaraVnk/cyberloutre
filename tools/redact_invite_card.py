#!/usr/bin/env python3
"""Redact credentials from the rendered invite card PDF.

Source : invite_card_A4.pdf rendered to PNG via pdftoppm (200 DPI → 1653×2339).
Output : a WebP usable on the public site where :
- the 3 QR codes are replaced with stylised placeholders (cannot be scanned)
- the visible WiFi password line is redacted

Run from project root :
    /usr/bin/python3 tools/redact_invite_card.py
"""
from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import Optional
import subprocess
import sys
import tempfile

PDF_SRC = Path("/Users/claravanacker/Projects/home-assistant/invite_card_A4.pdf")
OUT = Path(__file__).parent.parent / "static" / "img" / "smart-home" / "plexi-card.webp"

# Image dimensions after pdftoppm at 200 DPI : 1653 × 2339.
W, H = 1653, 2339

PLACEHOLDER_FILL = (235, 238, 245)       # light slate
PLACEHOLDER_BORDER = (180, 190, 210)
PLACEHOLDER_TEXT = (100, 110, 130)


def load_font(size: int, weight: str = "regular"):
    paths = {
        "bold": "/System/Library/Fonts/Helvetica.ttc",
        "regular": "/System/Library/Fonts/Helvetica.ttc",
    }
    try:
        return ImageFont.truetype(paths.get(weight, paths["regular"]), size)
    except Exception:
        return ImageFont.load_default()


def render_pdf_to_image(pdf: Path) -> Image.Image:
    """Use pdftoppm to render the PDF at 200 DPI, return PIL image."""
    with tempfile.TemporaryDirectory() as td:
        out_prefix = Path(td) / "out"
        subprocess.run(
            ["pdftoppm", "-r", "200", "-png", str(pdf), str(out_prefix)],
            check=True, capture_output=True,
        )
        rendered = next(Path(td).glob("out-*.png"))
        return Image.open(rendered).convert("RGB")


def redact_qr(draw: ImageDraw.ImageDraw, region, font_lock, font_label):
    left, top, right, bottom = region
    w = right - left
    h = bottom - top
    # Rounded white card background
    draw.rounded_rectangle(region, radius=24, fill=PLACEHOLDER_FILL,
                           outline=PLACEHOLDER_BORDER, width=3)
    # Centered "🔒  redacted" text. Use two lines for clarity.
    lock = "🔒"
    label = "QR masqué"
    sub = "(démo publique)"

    # Try to compute text positions roughly centered
    lock_bbox = draw.textbbox((0, 0), lock, font=font_lock)
    label_bbox = draw.textbbox((0, 0), label, font=font_label)
    sub_bbox = draw.textbbox((0, 0), sub, font=font_label)

    lock_w = lock_bbox[2] - lock_bbox[0]
    lock_h = lock_bbox[3] - lock_bbox[1]
    label_w = label_bbox[2] - label_bbox[0]
    sub_w = sub_bbox[2] - sub_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    sub_h = sub_bbox[3] - sub_bbox[1]

    total_h = lock_h + 20 + label_h + 8 + sub_h
    y_start = top + (h - total_h) // 2

    draw.text((left + (w - lock_w) // 2, y_start), lock, font=font_lock,
              fill=PLACEHOLDER_TEXT)
    draw.text((left + (w - label_w) // 2, y_start + lock_h + 20), label,
              font=font_label, fill=PLACEHOLDER_TEXT)
    draw.text((left + (w - sub_w) // 2, y_start + lock_h + 20 + label_h + 8), sub,
              font=font_label, fill=(150, 160, 180))


def redact_password(draw: ImageDraw.ImageDraw, region, font):
    left, top, right, bottom = region
    w = right - left
    h = bottom - top
    draw.rounded_rectangle(region, radius=10, fill=PLACEHOLDER_FILL,
                           outline=PLACEHOLDER_BORDER, width=2)
    label = "Visiteurs  /  ••••••••••••••••"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((left + (w - tw) // 2, top + (h - th) // 2 - 4),
              label, font=font, fill=PLACEHOLDER_TEXT)


def detect_qr_regions(img):
    """Find QR code bounding boxes by detecting rows with many black/white
    transitions (typical signature of a QR code's high-frequency pattern)."""
    gray = img.convert("L")
    w, h = gray.size
    pixels = gray.load()

    # Count transitions per row in the center horizontal band
    transitions = []
    for y in range(h):
        prev = pixels[0, y] < 128
        count = 0
        for x in range(1, w):
            curr = pixels[x, y] < 128
            if curr != prev:
                count += 1
            prev = curr
        transitions.append(count)

    # QR codes produce ~25-50 transitions per row at this rendering scale
    # Pure text rows have 0-15 transitions
    THRESHOLD = 25

    print(f"  Transition histogram: max={max(transitions)} median={sorted(transitions)[len(transitions)//2]}")
    high_rows = sum(1 for t in transitions if t >= THRESHOLD)
    print(f"  Rows above threshold {THRESHOLD}: {high_rows}")

    # Group consecutive rows above threshold (allow small gaps to bridge text inside QR)
    regions_y = []
    in_region = False
    region_start = 0
    gap = 0
    for y, t in enumerate(transitions):
        if t >= THRESHOLD:
            if not in_region:
                in_region = True
                region_start = y
            gap = 0
        else:
            if in_region:
                gap += 1
                if gap > 80:  # allow long gaps inside QR (quiet zones)
                    in_region = False
                    region_end = y - gap
                    if region_end - region_start > 200:  # min 200 rows tall
                        regions_y.append((region_start, region_end))
                    gap = 0
    if in_region and h - region_start > 200:
        regions_y.append((region_start, h))

    print(f"  Detected {len(regions_y)} candidate Y-regions: {regions_y}")

    # For each y-band, find x-extent by checking dark pixels
    regions = []
    for (y_start, y_end) in regions_y:
        # Find the leftmost & rightmost dark pixel across the band
        x_min, x_max = w, 0
        for y in range(y_start, y_end, 5):  # sample every 5 rows
            for x in range(w):
                if pixels[x, y] < 128:
                    if x < x_min:
                        x_min = x
                    break
            for x in range(w - 1, -1, -1):
                if pixels[x, y] < 128:
                    if x > x_max:
                        x_max = x
                    break
        # Add a small padding
        pad = 25
        regions.append((max(0, x_min - pad), max(0, y_start - pad),
                        min(w, x_max + pad), min(h, y_end + pad)))
    return regions


def detect_password_line(img, qr_bottom):
    """Find the password line just below the first QR. It's a horizontal text
    line, identifiable as a thin band of dark pixels under qr_bottom."""
    gray = img.convert("L")
    w, h = gray.size
    pixels = gray.load()

    # Scan down from qr_bottom to find a row with text (some dark pixels)
    for y in range(qr_bottom, min(qr_bottom + 200, h)):
        dark_count = sum(1 for x in range(w) if pixels[x, y] < 100)
        if 30 < dark_count < w * 0.5:  # text-ish density
            # Find the band of text
            band_start = y
            for y2 in range(y, min(y + 100, h)):
                dark2 = sum(1 for x in range(w) if pixels[x, y2] < 100)
                if dark2 < 5:
                    return (300, band_start - 15, w - 300, y2 + 15)
            return (300, band_start - 15, w - 300, y + 80)
    return None


def main():
    if not PDF_SRC.exists():
        print(f"✗ PDF not found: {PDF_SRC}", file=sys.stderr)
        sys.exit(1)

    img = render_pdf_to_image(PDF_SRC)
    if img.size != (W, H):
        print(f"⚠ Unexpected size {img.size}, expected {(W, H)}", file=sys.stderr)

    print("Detecting QR code regions…")
    qr_regions = detect_qr_regions(img)
    for i, r in enumerate(qr_regions):
        print(f"  QR {i+1}: x=({r[0]},{r[2]}) y=({r[1]},{r[3]})  →  {r[2]-r[0]}×{r[3]-r[1]}")

    # The password line is right below QR 1
    pw_region = None
    if qr_regions:
        pw_region = detect_password_line(img, qr_regions[0][3] + 10)
        if pw_region:
            print(f"  PW: x=({pw_region[0]},{pw_region[2]}) y=({pw_region[1]},{pw_region[3]})")

    draw = ImageDraw.Draw(img)
    font_lock = load_font(80)
    font_label = load_font(38, "bold")
    font_pw = load_font(34, "bold")

    for region in qr_regions:
        redact_qr(draw, region, font_lock, font_label)
    if pw_region:
        redact_password(draw, pw_region, font_pw)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "WEBP", quality=85, method=6)
    print(f"✓ Redacted card saved → {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
