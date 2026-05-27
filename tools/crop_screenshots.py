#!/usr/bin/env python3
"""Auto-crop iOS chrome (status bar + HA white app header) from screenshots.

For each mobile screenshot, finds the first/last row where the content
transitions from white (iOS + HA header) to dark navy (HA dashboard content),
then crops accordingly and re-encodes as WebP.

The phone mockup CSS aspect-ratio must be updated to match the resulting
cropped aspect ratio.

Run from project root:
    /usr/bin/python3 tools/crop_screenshots.py
"""
from PIL import Image
from pathlib import Path
import sys

SRC_DIR = Path("/Users/claravanacker/Projects/home-assistant")
DST_DIR = Path(__file__).parent.parent / "static" / "img" / "smart-home"

# Mapping src PNG → dst WebP (kebab-case rename, same as before)
MAPPING = [
    ("dashboard_showcase_mobile_1.png", "showcase-1.webp"),
    ("dashboard_showcase_mobile_2.png", "showcase-2.webp"),
    ("dashboard_showcase_mobile_3.png", "showcase-3.webp"),
    ("dashboard_showcase_mobile_4.png", "showcase-4.webp"),
    ("dashboard_showcase_mobile_5.png", "showcase-5.webp"),
    ("dashboard_showcase_mobile_6.png", "showcase-6.webp"),
    ("dashboard_calendrier_mobile.png", "calendrier.webp"),
    ("dashboard_colis_mobile.png", "colis.webp"),
    ("dashboard_energie_mobile_1.png", "energie-1.webp"),
    ("dashboard_energie_mobile_2.png", "energie-2.webp"),
    ("dashboard_energie_mobile_3.png", "energie-3.webp"),
    ("dashboard_graph_energie_mobile_1.png", "energie-graph-1.webp"),
    ("dashboard_graph_energie_mobile_2.png", "energie-graph-2.webp"),
    ("dashboard_tempo_mobile_1.png", "tempo-1.webp"),
    ("dashboard_tempo_mobile_2.png", "tempo-2.webp"),
    ("dashboard_robot_mobile_1.png", "robot-1.webp"),
    ("dashboard_robot_mobile_2.png", "robot-2.webp"),
    ("dashboard_robot_mobile_3.png", "robot-3.webp"),
    ("dashboard_tesla_mobile_1.png", "tesla-1.webp"),
    ("dashboard_tesla_mobile_2.png", "tesla-2.webp"),
    ("dashboard_tesla_mobile_3.png", "tesla-3.webp"),
    ("dashboard_tesla_mobile_4.png", "tesla-4.webp"),
    ("dashboard_maintenance_mobile_1.png", "maintenance-1.webp"),
    ("dashboard_maintenance_mobile_2.png", "maintenance-2.webp"),
    ("dashboard_maintenance_mobile_3.png", "maintenance-3.webp"),
    ("dashboard_prusa_mobile_1.png", "prusa-1.webp"),
    ("dashboard_prusa_mobile_2.png", "prusa-2.webp"),
    ("dashboard_prusa_mobile_3.png", "prusa-3.webp"),
    ("dashbaord_batteries_mobile.png", "batteries.webp"),
]

# A row is considered "light" (= part of the white header bar) if its mean
# brightness ≥ this threshold. White is ~240, pink content ~200, navy ~50.
LIGHT_THRESHOLD = 220

# Default crop for screenshots that start with dark content (no white header,
# just iOS status bar overlaying the dashboard) — iPhone 15/16 status bar.
DEFAULT_DARK_TOP_CROP = 180

# Max look-ahead for finding the end of the white header
MAX_HEADER_SCAN = 700


def row_brightness(img: Image.Image, row: int) -> float:
    """Mean brightness of one row across width and RGB channels."""
    line = img.crop((0, row, img.width, row + 1)).convert("RGB")
    pixels = list(line.getdata())
    total = sum(p[0] + p[1] + p[2] for p in pixels)
    return total / (len(pixels) * 3)


def find_top_crop(img: Image.Image) -> int:
    """Find where to crop the top.

    Two cases :
    - If the image starts LIGHT (white iOS status bar + white HA app header),
      find where the light area ends and crop there.
    - If the image starts DARK (immersive dashboard, status bar overlay), crop
      a fixed amount for the iOS status bar.
    """
    h = img.height
    starts_light = row_brightness(img, 0) >= LIGHT_THRESHOLD

    if starts_light:
        # Need many consecutive "non-light" rows to confirm we've left the
        # white header. Status bar icons/text give brief dips of ~5-20 rows
        # so we require at least 40 rows of continuous non-light to consider
        # we've reached the dashboard content.
        consecutive_dark_needed = 40
        consecutive_dark = 0
        first_dark_y = None
        for y in range(1, min(MAX_HEADER_SCAN, h)):
            if row_brightness(img, y) < LIGHT_THRESHOLD:
                if consecutive_dark == 0:
                    first_dark_y = y
                consecutive_dark += 1
                if consecutive_dark >= consecutive_dark_needed:
                    return first_dark_y
            else:
                consecutive_dark = 0
                first_dark_y = None
        # Fallback : crop the typical header height
        return 350
    else:
        return DEFAULT_DARK_TOP_CROP


def find_bottom_crop(img: Image.Image) -> int:
    """Look at the bottom rows : if they're light (white home indicator on top
    of light theme, or pure white area at end of content), crop them off."""
    h = img.height
    for y in range(h - 1, max(h - 400, 0), -1):
        if row_brightness(img, y) < LIGHT_THRESHOLD:
            return y + 1  # last row with content, +1 because crop is exclusive
    return h  # no light area at bottom → keep everything


def process_one(src: Path, dst: Path) -> tuple[int, int, int, int]:
    """Process one image. Returns (orig_h, top_crop, bottom_crop, new_h)."""
    img = Image.open(src)
    orig_w, orig_h = img.size

    top = find_top_crop(img)
    bottom = find_bottom_crop(img)

    if bottom - top < orig_h * 0.5:
        # Sanity check : crop seems crazy, fall back to default
        print(f"  ⚠ {src.name}: crop suspect (top={top}, bottom={bottom}), fallback")
        top = MIN_TOP_CROP
        bottom = orig_h

    cropped = img.crop((0, top, orig_w, bottom))
    cropped.save(dst, "WEBP", quality=80, method=6)
    return orig_h, top, bottom, cropped.height


def main():
    if not SRC_DIR.exists():
        print(f"✗ Source folder not found: {SRC_DIR}", file=sys.stderr)
        sys.exit(1)
    DST_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Cropping {len(MAPPING)} screenshots…\n")
    print(f"{'file':<40} {'orig_h':>7} {'top':>5} {'bot':>5} {'new_h':>7}  ratio")
    print("-" * 80)
    tops = []
    new_heights = []
    for src_name, dst_name in MAPPING:
        src = SRC_DIR / src_name
        dst = DST_DIR / dst_name
        if not src.exists():
            print(f"  ⚠ Missing: {src_name}")
            continue
        orig_h, top, bottom, new_h = process_one(src, dst)
        tops.append(top)
        new_heights.append(new_h)
        ratio = 1206 / new_h
        print(f"{dst_name:<40} {orig_h:>7} {top:>5} {bottom:>5} {new_h:>7}  {ratio:.3f}")

    if tops:
        avg_top = sum(tops) / len(tops)
        avg_new_h = sum(new_heights) / len(new_heights)
        print(f"\nAvg top crop: {avg_top:.0f}px  ·  Avg new height: {avg_new_h:.0f}px")
        print(f"Suggested CSS aspect-ratio for cropped images: 1206 / {round(avg_new_h)}")


if __name__ == "__main__":
    main()
