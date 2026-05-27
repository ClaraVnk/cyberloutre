#!/usr/bin/env python3
"""Process the 3 welcome page screenshots (visitor onboarding).

For each screenshot :
1. Auto-crop the iOS status bar at the top
2. Detect QR code(s) and replace with a stylised placeholder (so they can't
   be scanned from cyberloutre.fr)
3. Detect the visible Wi-Fi / dashboard password line and redact it
4. Save as WebP

Source PNG names expected in /Users/claravanacker/Projects/home-assistant/ :
    welcome_wifi_mobile.png       → welcome-wifi.webp       (Wi-Fi step)
    welcome_dashboard_mobile.png  → welcome-dashboard.webp  (dashboard step)
    welcome_app_mobile.png        → welcome-app.webp        (HA app step)

Run :
    /usr/bin/python3 tools/process_welcome_screenshots.py
"""
from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import sys

DST_DIR = Path(__file__).parent.parent / "static" / "img" / "smart-home"

# Welcome page screenshots (visitor onboarding) — Page_invite*.jpg are in
# /Users/claravanacker/Projects/ at the moment.
WELCOME_MAPPING = [
    (Path("/Users/claravanacker/Projects/Page_invite1.jpg"), "welcome-wifi.webp"),
    (Path("/Users/claravanacker/Projects/Page_invite2.jpg"), "welcome-dashboard.webp"),
    (Path("/Users/claravanacker/Projects/Page_invite3.jpg"), "welcome-app.webp"),
]

# Tesla-4 contains a map showing Loutre's house in Saint-Julien-en-Genevois.
# We blur the map tiles in-place on the already-cropped WebP.
TESLA_MAP_FILE = DST_DIR / "tesla-4.webp"
# Approximate coordinates of the map area in tesla-4.webp (1206 × 2267).
# Crops just inside the rounded card so the title and copyright stay legible.
TESLA_MAP_REGION = (45, 280, 1160, 1015)

# Page_invite*.jpg are already cropped exports (no iOS status bar present).
IOS_STATUS_BAR_HEIGHT = 0

PLACEHOLDER_FILL = (245, 247, 252)
PLACEHOLDER_BORDER = (200, 210, 225)
PLACEHOLDER_TEXT = (110, 120, 140)
PLACEHOLDER_TEXT_DIM = (160, 170, 190)


def load_font(size: int):
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
    ]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def row_transitions(pixels, y, w):
    """Count black/white transitions on row y (helps find QR codes)."""
    prev = pixels[0, y] < 128
    count = 0
    for x in range(1, w):
        curr = pixels[x, y] < 128
        if curr != prev:
            count += 1
        prev = curr
    return count


def detect_qr_region(img, debug=False):
    """Find the QR code bounding box using two signatures :
    - dark pixel density per row : ~40-60% on QR rows, <15% on text rows
    - dark pixel x-spread per row : QR spans >400px wide, text spans <400px
    """
    gray = img.convert("L")
    w, h = gray.size
    pixels = gray.load()

    DARK_PCT_MIN = 0.20    # QR rows have at least 20% dark pixels
    DARK_PCT_MAX = 0.70    # but not solid black (which would be a black bar)
    MIN_X_SPREAD = w * 0.4  # dark pixels must span at least 40% of the width
    MIN_HEIGHT = 200

    # Pre-compute per row : dark pixel %, leftmost dark x, rightmost dark x
    row_info = []
    for y in range(h):
        count = 0
        x_min, x_max = w, 0
        for x in range(w):
            if pixels[x, y] < 128:
                count += 1
                if x < x_min:
                    x_min = x
                if x > x_max:
                    x_max = x
        pct = count / w
        spread = x_max - x_min if x_max >= x_min else 0
        row_info.append((pct, x_min, x_max, spread))

    if debug:
        qr_like_count = sum(1 for (p, _, _, s) in row_info
                            if DARK_PCT_MIN <= p <= DARK_PCT_MAX and s >= MIN_X_SPREAD)
        print(f"    rows QR-like: {qr_like_count}/{h}")

    # Find contiguous QR-like rows
    candidates = []
    in_region = False
    start = 0
    gap = 0
    for y, (pct, _, _, spread) in enumerate(row_info):
        qr_like = (DARK_PCT_MIN <= pct <= DARK_PCT_MAX and spread >= MIN_X_SPREAD)
        if qr_like:
            if not in_region:
                in_region = True
                start = y
            gap = 0
        else:
            if in_region:
                gap += 1
                if gap > 40:
                    in_region = False
                    end = y - gap
                    if end - start >= MIN_HEIGHT:
                        candidates.append((start, end))
                    gap = 0
    if in_region and h - start >= MIN_HEIGHT:
        candidates.append((start, h))

    if debug:
        print(f"    candidates: {candidates}")

    if not candidates:
        return None
    y_start, y_end = max(candidates, key=lambda r: r[1] - r[0])

    # X-extent : take the most common x_min / x_max across QR rows (mode-like),
    # ignoring outliers from card borders / shadows near the image edges.
    # We compute the MEDIAN x_min and MEDIAN x_max from the QR rows only.
    qr_row_xs = []
    for y in range(y_start, y_end):
        pct, xl, xr, spread = row_info[y]
        if DARK_PCT_MIN <= pct <= DARK_PCT_MAX and spread >= MIN_X_SPREAD:
            qr_row_xs.append((xl, xr))

    if not qr_row_xs:
        return None

    # Sort and take median
    x_mins = sorted(xl for (xl, _) in qr_row_xs)
    x_maxs = sorted(xr for (_, xr) in qr_row_xs)
    x_min = x_mins[len(x_mins) // 2]
    x_max = x_maxs[len(x_maxs) // 2]

    # Enforce QR-shape constraint : QRs are square, height ≈ width.
    # If detected width is significantly larger than height (= shadow / card
    # noise on the side), clamp to height and re-center on the image's
    # horizontal midpoint.
    height = y_end - y_start
    width = x_max - x_min
    if width > height * 1.15:
        center_x = w // 2
        half = height // 2
        x_min = center_x - half
        x_max = center_x + half

    pad = 30
    return (max(0, x_min - pad), max(0, y_start - pad),
            min(w, x_max + pad), min(h, y_end + pad))


def detect_password_line(img, search_from_y):
    """Find the password text — the last text line before the bottom of the
    image. On welcome screens 1 and 2 it's a monospace string ; the row has
    moderate dark density concentrated on the right half (after the label).
    """
    gray = img.convert("L")
    w, h = gray.size
    pixels = gray.load()

    # Scan from bottom up, find the last block of text
    text_rows = []
    for y in range(h - 1, search_from_y, -1):
        count = sum(1 for x in range(w) if pixels[x, y] < 100)
        if 20 < count < w * 0.35:
            text_rows.append(y)

    if not text_rows:
        return None

    # Group adjacent rows into bands (close rows)
    text_rows.sort()
    bands = []
    band = [text_rows[0]]
    for y in text_rows[1:]:
        if y - band[-1] <= 6:
            band.append(y)
        else:
            bands.append((band[0], band[-1]))
            band = [y]
    bands.append((band[0], band[-1]))

    # Filter : keep bands at least 30 rows tall (real text lines)
    sized = [(a, b) for (a, b) in bands if b - a >= 30]
    if not sized:
        return None

    # Merge bands separated by < 250 rows : the password may be wrapped on
    # 2 lines AND there's often a small "t" tail far below the main line.
    merged = [sized[0]]
    for b in sized[1:]:
        prev_start, prev_end = merged[-1]
        if b[0] - prev_end < 250:
            merged[-1] = (prev_start, b[1])
        else:
            merged.append(b)

    # Pick the LARGEST merged group (= the full credentials area, which is
    # bigger than any random standalone text band like "t")
    band_start, band_end = max(merged, key=lambda r: r[1] - r[0])
    # Add generous bottom padding to catch any remaining wrapped tail
    return (220, max(0, band_start - 20), w - 80, min(h, band_end + 60))


def redact_qr(img, region):
    """Replace the QR code area with a clean light placeholder."""
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = region
    w_r = right - left
    h_r = bottom - top
    draw.rounded_rectangle(region, radius=40, fill=PLACEHOLDER_FILL,
                           outline=PLACEHOLDER_BORDER, width=4)
    font_lock = load_font(140)
    font_label = load_font(56)
    font_sub = load_font(38)
    lock = "🔒"
    label = "QR masqué"
    sub = "(démo publique)"

    lock_bbox = draw.textbbox((0, 0), lock, font=font_lock)
    label_bbox = draw.textbbox((0, 0), label, font=font_label)
    sub_bbox = draw.textbbox((0, 0), sub, font=font_sub)
    lock_w = lock_bbox[2] - lock_bbox[0]; lock_h = lock_bbox[3] - lock_bbox[1]
    label_w = label_bbox[2] - label_bbox[0]; label_h = label_bbox[3] - label_bbox[1]
    sub_w = sub_bbox[2] - sub_bbox[0]; sub_h = sub_bbox[3] - sub_bbox[1]

    total_h = lock_h + 30 + label_h + 14 + sub_h
    y0 = top + (h_r - total_h) // 2
    draw.text((left + (w_r - lock_w) // 2, y0), lock, font=font_lock, fill=PLACEHOLDER_TEXT)
    draw.text((left + (w_r - label_w) // 2, y0 + lock_h + 30), label,
              font=font_label, fill=PLACEHOLDER_TEXT)
    draw.text((left + (w_r - sub_w) // 2, y0 + lock_h + 30 + label_h + 14), sub,
              font=font_sub, fill=PLACEHOLDER_TEXT_DIM)


def redact_password(img, region):
    """Overlay a clean placeholder over the password line."""
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = region
    w_r = right - left
    h_r = bottom - top
    draw.rounded_rectangle(region, radius=12, fill=PLACEHOLDER_FILL,
                           outline=PLACEHOLDER_BORDER, width=2)
    font = load_font(48)
    label = "••••••••••••••••"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((left + (w_r - tw) // 2, top + (h_r - th) // 2 - 6),
              label, font=font, fill=PLACEHOLDER_TEXT)


def process_one(src: Path, dst: Path):
    img = Image.open(src).convert("RGB")
    w, h = img.size

    # Crop iOS status bar
    img = img.crop((0, IOS_STATUS_BAR_HEIGHT, w, h))

    # Detect & redact QR
    qr = detect_qr_region(img, debug=True)
    if qr:
        print(f"  QR detected at {qr}")
        redact_qr(img, qr)
        # Look for password line below the QR
        pw = detect_password_line(img, qr[3] + 30)
        if pw:
            print(f"  Password line at {pw}")
            redact_password(img, pw)
        else:
            print(f"  No password line detected (may be the App QR — no creds)")
    else:
        print(f"  ⚠ No QR detected in {src.name}")

    img.save(dst, "WEBP", quality=85, method=6)
    print(f"  ✓ {dst.name}  ({dst.stat().st_size // 1024} KB)")


def blur_tesla_map():
    """Blur the map region in tesla-4.webp (in place). The map reveals the
    home's location in Saint-Julien-en-Genevois — sensitive info."""
    if not TESLA_MAP_FILE.exists():
        print(f"\n⚠ {TESLA_MAP_FILE.name} not found, skipping Tesla map blur")
        return

    print(f"\n→ Blurring map region in {TESLA_MAP_FILE.name}")
    img = Image.open(TESLA_MAP_FILE).convert("RGB")
    # Extract the map region
    region = img.crop(TESLA_MAP_REGION)
    # Apply heavy blur (pixelate-like) — radius 25 makes street names unreadable
    blurred = region.filter(ImageFilter.GaussianBlur(radius=30))
    # Paste back into the image
    img.paste(blurred, (TESLA_MAP_REGION[0], TESLA_MAP_REGION[1]))
    # Add a discreet overlay text on the blurred area
    draw = ImageDraw.Draw(img)
    font = load_font(48)
    label = "📍 localisation floutée"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = TESLA_MAP_REGION[0] + ((TESLA_MAP_REGION[2] - TESLA_MAP_REGION[0]) - tw) // 2
    y = TESLA_MAP_REGION[1] + ((TESLA_MAP_REGION[3] - TESLA_MAP_REGION[1]) - th) // 2 - 8
    # Soft pill background for readability
    pill_pad_x, pill_pad_y = 24, 12
    pill = (x - pill_pad_x, y - pill_pad_y, x + tw + pill_pad_x, y + th + pill_pad_y)
    draw.rounded_rectangle(pill, radius=20, fill=(15, 17, 25, 200))
    draw.text((x, y), label, font=font, fill=(232, 234, 240))
    img.save(TESLA_MAP_FILE, "WEBP", quality=85, method=6)
    print(f"  ✓ {TESLA_MAP_FILE.name} updated")


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)

    missing = []
    for src, dst_name in WELCOME_MAPPING:
        if not src.exists():
            missing.append(str(src))
            continue
        print(f"\n→ Processing {src.name}")
        process_one(src, DST_DIR / dst_name)

    if missing:
        print(f"\n⚠ Welcome files not found:")
        for m in missing:
            print(f"  - {m}")

    blur_tesla_map()


if __name__ == "__main__":
    main()
