"""Generate a 1080x1080 Instagram card from curated newsletter data."""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1080

# Color palette matching the newsletter
BG_DARK    = (26,  17,  23)   # #1a1117
BG_CARD    = (30,  30,  42)   # #1e1e2a
BURGUNDY   = (139,  0,   0)   # #8B0000
GOLD       = (255, 215,  0)   # #FFD700
GOLD_LIGHT = (255, 236, 179)  # #ffecb3
TEXT_LIGHT = (232, 224, 212)  # #e8e0d4
TEXT_DIM   = (180, 176, 180)  # #b8b0b4

_BOLD_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",   # Ubuntu CI
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",              # macOS
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_REGULAR_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (_BOLD_PATHS if bold else _REGULAR_PATHS):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _text_h(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


def _center_text(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill: tuple):
    x = (W - _text_w(draw, text, font)) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_px: int) -> str:
    if _text_w(draw, text, font) <= max_px:
        return text
    while len(text) > 4 and _text_w(draw, text + "…", font) > max_px:
        text = text[:-1]
    return text + "…"


def generate_image(curated: dict, date_range: str, output_path: str) -> str:
    """Render a 1080x1080 PNG and save it to output_path. Returns the path."""
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # ── Header ────────────────────────────────────────────────────────────
    HEADER_H = 210
    draw.rectangle([0, 0, W, HEADER_H], fill=BURGUNDY)
    draw.rectangle([0, HEADER_H - 4, W, HEADER_H], fill=GOLD)

    f_title    = _font(80, bold=True)
    f_subtitle = _font(34)
    f_date     = _font(28)

    _center_text(draw, "OUR SCENE", 24, f_title, GOLD)
    _center_text(draw, "NYC · IMPROV & SKETCH", 120, f_subtitle, GOLD_LIGHT)
    _center_text(draw, date_range, 166, f_date, GOLD_LIGHT)

    # ── Show cards ────────────────────────────────────────────────────────
    FOOTER_H = 88
    PAD = 40
    CARD_W = W - PAD * 2
    CARD_GAP = 14
    CARD_INNER = 16
    CARD_H = 100

    f_meta  = _font(27)
    f_show  = _font(36, bold=True)

    # Collect up to 5 shows: starred first, then rest
    all_shows: list[dict] = []
    for day in (curated.get("days") or []):
        short_day = day.get("label", "").split(",")[0]
        for show in (day.get("shows") or []):
            all_shows.append({**show, "_day": short_day})

    starred = [s for s in all_shows if s.get("starred")]
    rest    = [s for s in all_shows if not s.get("starred")]
    top = (starred + rest)[:5]

    y = HEADER_H + 28
    shown = 0
    for show in top:
        if y + CARD_H > H - FOOTER_H - 10:
            break

        draw.rounded_rectangle(
            [PAD, y, PAD + CARD_W, y + CARD_H],
            radius=10, fill=BG_CARD,
        )

        day_s   = show.get("_day", "")
        time_s  = show.get("time", "")
        venue_s = show.get("venue", "")
        title_s = show.get("title", "")
        star    = "★ " if show.get("starred") else ""

        meta = f"{star}{day_s}  ·  {time_s}  ·  {venue_s}"
        meta = _truncate(draw, meta, f_meta, CARD_W - CARD_INNER * 2)
        draw.text((PAD + CARD_INNER, y + 10), meta, font=f_meta, fill=GOLD)

        title_s = _truncate(draw, title_s, f_show, CARD_W - CARD_INNER * 2)
        draw.text((PAD + CARD_INNER, y + 46), title_s, font=f_show, fill=TEXT_LIGHT)

        y += CARD_H + CARD_GAP
        shown += 1

    remaining = len(all_shows) - shown
    if remaining > 0:
        f_more = _font(26)
        more = f"+ {remaining} more show{'s' if remaining != 1 else ''} in this week's newsletter →"
        draw.text((PAD, y + 4), more, font=f_more, fill=TEXT_DIM)

    # ── Footer ────────────────────────────────────────────────────────────
    draw.rectangle([0, H - FOOTER_H, W, H], fill=BURGUNDY)
    draw.rectangle([0, H - FOOTER_H, W, H - FOOTER_H + 3], fill=GOLD)

    f_footer = _font(36, bold=True)
    _center_text(draw, "@ourscenenyc", H - FOOTER_H + 24, f_footer, GOLD)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"📸 Instagram image saved: {output_path}")
    return output_path
