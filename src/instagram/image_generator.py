"""Generate Instagram carousel slides from curated newsletter data.

Produces:
  - One cover slide  (brand + date range + swipe CTA)
  - One slide per day  (day header + up to 4 show cards)

All slides are 1080x1080 px in the newsletter's burgundy/gold aesthetic.
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1080

# ── Palette ───────────────────────────────────────────────────────────────────
BG_DARK    = (26,  17,  23)
BG_CARD    = (30,  30,  42)
BG_CARD_2  = (36,  32,  50)   # alternate card for starred shows
BURGUNDY   = (139,  0,   0)
GOLD       = (255, 215,  0)
GOLD_LIGHT = (255, 236, 179)
GOLD_DIM   = (180, 150,  60)
TEXT_WHITE = (240, 234, 228)
TEXT_DIM   = (160, 152, 168)
FREE_GREEN = (120, 210, 130)

# ── Font paths ─────────────────────────────────────────────────────────────────
_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
_REG = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _font(size: int, bold: bool = False):
    for p in (_BOLD if bold else _REG):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _th(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


def _center(draw, text, y, font, fill):
    draw.text(((W - _tw(draw, text, font)) // 2, y), text, font=font, fill=fill)


def _trunc(draw, text, font, max_px):
    if _tw(draw, text, font) <= max_px:
        return text
    while len(text) > 4 and _tw(draw, text + "…", font) > max_px:
        text = text[:-1]
    return text + "…"


def _footer(draw, font):
    draw.rectangle([0, H - 70, W, H], fill=BURGUNDY)
    draw.rectangle([0, H - 70, W, H - 67], fill=GOLD)
    _center(draw, "@ourscenenyc", H - 48, font, GOLD)


# ── Cover slide ───────────────────────────────────────────────────────────────

def generate_cover_slide(curated: dict, date_range: str, output_path: str) -> str:
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Top burgundy band
    BAND_H = 260
    draw.rectangle([0, 0, W, BAND_H], fill=BURGUNDY)
    draw.rectangle([0, BAND_H - 4, W, BAND_H], fill=GOLD)

    f_brand   = _font(86, bold=True)
    f_sub     = _font(34)
    f_date    = _font(42, bold=True)
    f_stats   = _font(28)
    f_swipe   = _font(30)
    f_footer  = _font(32, bold=True)

    _center(draw, "OUR SCENE", 22, f_brand, GOLD)
    _center(draw, "NYC · IMPROV & SKETCH", 126, f_sub, GOLD_LIGHT)
    _center(draw, "✦  Every week, curated  ✦", 176, _font(24), GOLD_DIM)

    # Date range
    _center(draw, date_range, 310, f_date, TEXT_WHITE)

    # Stats bar
    total_shows = sum(len(d.get("shows") or []) for d in (curated.get("days") or []))
    days_count  = len(curated.get("days") or [])
    _center(draw,
            f"{total_shows} picks  ·  {days_count} nights",
            374, f_stats, GOLD_LIGHT)

    # Day chips
    PAD_X = 60
    chip_y = 450
    f_chip = _font(26, bold=True)
    chip_gap = 12
    days = curated.get("days") or []

    # Measure total width to center the row
    chip_rects = []
    for day in days:
        short = (day.get("label", "").split(",")[0] or "").upper()
        em    = day.get("emoji", "")
        label = f"{em} {short}" if em else short
        tw    = _tw(draw, label, f_chip)
        chip_rects.append((label, tw + 24))   # 24px horizontal padding

    total_chips_w = sum(w for _, w in chip_rects) + chip_gap * (len(chip_rects) - 1)
    cx = (W - total_chips_w) // 2

    for label, cw in chip_rects:
        draw.rounded_rectangle([cx, chip_y, cx + cw, chip_y + 46],
                                radius=6, fill=BG_CARD)
        draw.text((cx + 12, chip_y + 8), label, font=f_chip, fill=GOLD)
        cx += cw + chip_gap

    # Swipe CTA
    cta_y = 560
    draw.rounded_rectangle([W//2 - 220, cta_y, W//2 + 220, cta_y + 60],
                            radius=30, fill=BURGUNDY)
    draw.rounded_rectangle([W//2 - 220, cta_y, W//2 + 220, cta_y + 60],
                            radius=30, outline=GOLD, width=2)
    _center(draw, "Swipe for each night  →", cta_y + 14, f_swipe, GOLD)

    # Submission CTA
    _center(draw, "Got a show? DM us or reply to the newsletter",
            660, _font(24), TEXT_DIM)

    _footer(draw, f_footer)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


# ── Day slide ─────────────────────────────────────────────────────────────────

_FORMAT_EMOJI = {
    "improv":      "🎭",
    "sketch":      "✏️",
    "open_mic":    "🎤",
    "variety":     "🎪",
    "standup":     "🎤",
    "class_show":  "📚",
    "jam":         "🎲",
}


def generate_day_slide(day: dict, output_path: str) -> str:
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    label    = day.get("label", "")
    emoji    = day.get("emoji", "🎭")
    shows    = (day.get("shows") or [])[:4]   # max 4 per slide
    overflow = max(0, len(day.get("shows") or []) - 4)

    f_day_name = _font(52, bold=True)
    f_meta     = _font(26)
    f_venue    = _font(30, bold=True)
    f_title    = _font(36, bold=True)
    f_detail   = _font(24)
    f_footer   = _font(32, bold=True)

    # ── Day header ────────────────────────────────────────────────────────────
    HDR_H = 116
    draw.rectangle([0, 0, W, HDR_H], fill=BURGUNDY)
    draw.rectangle([0, HDR_H - 3, W, HDR_H], fill=GOLD)

    short_label = label.upper()
    hdr_text    = f"{emoji}  {short_label}"
    draw.text((40, 28), hdr_text, font=f_day_name, fill=GOLD)

    # ── Show cards ────────────────────────────────────────────────────────────
    PAD   = 24       # horizontal padding
    GAP   = 12       # gap between cards
    CARD_W = W - PAD * 2
    FOOTER_H = 70

    # Distribute remaining height among cards
    body_h  = H - HDR_H - FOOTER_H - GAP
    n       = len(shows)
    if n == 0:
        _footer(draw, f_footer)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img.save(output_path, "PNG")
        return output_path

    card_h  = (body_h - GAP * (n - 1) - (36 if overflow else 0)) // n

    y = HDR_H + GAP

    for show in shows:
        time_s    = show.get("time", "TBA")
        venue_s   = show.get("venue", "")
        title_s   = show.get("title", "")
        starred   = bool(show.get("starred"))
        details_s = show.get("details", "")
        price_s   = show.get("price", "")
        is_free   = "free" in (price_s or title_s or "").lower()

        from src.venues import lookup as venue_lookup
        neighborhood, _ = venue_lookup(venue_s)

        bg = BG_CARD_2 if starred else BG_CARD
        draw.rounded_rectangle([PAD, y, PAD + CARD_W, y + card_h],
                                radius=8, fill=bg)

        inner_x = PAD + 16
        inner_w = CARD_W - 32
        cy = y + 14

        # Meta line: time · neighborhood
        badges = []
        if starred: badges.append("⭐")
        if is_free:  badges.append("🆓")
        badge_str  = " ".join(badges)
        meta_parts = [time_s, neighborhood]
        meta_text  = "  ·  ".join(p for p in meta_parts if p)
        if badge_str:
            meta_text = f"{badge_str}  {meta_text}"
        draw.text((inner_x, cy), _trunc(draw, meta_text, f_meta, inner_w),
                  font=f_meta, fill=GOLD)
        cy += _th(draw, meta_text, f_meta) + 8

        # Venue line
        draw.text((inner_x, cy),
                  _trunc(draw, venue_s, f_venue, inner_w),
                  font=f_venue, fill=GOLD_LIGHT)
        cy += _th(draw, venue_s, f_venue) + 8

        # Title
        draw.text((inner_x, cy),
                  _trunc(draw, title_s, f_title, inner_w),
                  font=f_title, fill=TEXT_WHITE)
        cy += _th(draw, title_s, f_title) + 8

        # Details (if space remains)
        remaining = (y + card_h) - cy - 14
        if details_s and remaining >= _th(draw, "A", f_detail) + 4:
            draw.text((inner_x, cy),
                      _trunc(draw, details_s, f_detail, inner_w),
                      font=f_detail, fill=TEXT_DIM)

        y += card_h + GAP

    # Overflow note
    if overflow:
        draw.text((PAD, y + 4),
                  f"+ {overflow} more show{'s' if overflow > 1 else ''} in this week's newsletter →",
                  font=_font(25), fill=TEXT_DIM)

    _footer(draw, f_footer)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


# ── Signup CTA slide ──────────────────────────────────────────────────────────

def generate_signup_slide(output_path: str) -> str:
    """Final carousel slide: newsletter signup CTA."""
    img = Image.new("RGB", (W, H), BURGUNDY)
    draw = ImageDraw.Draw(img)

    # Gold border frame
    B = 28
    draw.rectangle([B, B, W - B, H - B], outline=GOLD, width=3)
    draw.rectangle([B + 8, B + 8, W - B - 8, H - B - 8], outline=GOLD_DIM, width=1)

    f_headline = _font(72, bold=True)
    f_sub      = _font(36)
    f_body     = _font(30)
    f_cta      = _font(38, bold=True)
    f_handle   = _font(34)

    _center(draw, "Want the full picks", 160, f_headline, GOLD)
    _center(draw, "every week?", 250, f_headline, GOLD)

    _center(draw, "The newsletter goes deeper —", 380, f_sub, GOLD_LIGHT)
    _center(draw, "descriptions, times, every show,", 426, f_sub, GOLD_LIGHT)
    _center(draw, "straight to your inbox.", 472, f_sub, GOLD_LIGHT)

    # CTA box
    box_y = 560
    draw.rounded_rectangle([120, box_y, W - 120, box_y + 80],
                            radius=40, fill=BG_DARK)
    draw.rounded_rectangle([120, box_y, W - 120, box_y + 80],
                            radius=40, outline=GOLD, width=2)
    _center(draw, "🔗  Link in bio to subscribe", box_y + 20, f_cta, GOLD)

    _center(draw, "Free · Weekly · No spam", 680, f_body, GOLD_DIM)

    # Divider
    draw.line([200, 740, W - 200, 740], fill=GOLD_DIM, width=1)

    _center(draw, "Got a show to feature?", 768, f_body, GOLD_LIGHT)
    _center(draw, "DM us or reply to any newsletter", 808, f_body, GOLD_LIGHT)

    _center(draw, "@ourscenenyc", 890, f_handle, GOLD)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


# ── Carousel entry point ──────────────────────────────────────────────────────

def generate_carousel(curated: dict, date_range: str, output_dir: str) -> list[str]:
    """Generate all carousel slides. Returns list of file paths in order.

    Slide order: cover → one per day → signup CTA
    Instagram allows up to 10 slides; with 7 days that's 9 total — within limit.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []

    cover = os.path.join(output_dir, "00_cover.png")
    generate_cover_slide(curated, date_range, cover)
    paths.append(cover)

    for i, day in enumerate(curated.get("days") or [], start=1):
        date_iso   = day.get("date_iso", f"day{i:02d}")
        slide_path = os.path.join(output_dir, f"{i:02d}_{date_iso}.png")
        generate_day_slide(day, slide_path)
        paths.append(slide_path)

    signup = os.path.join(output_dir, "99_signup.png")
    generate_signup_slide(signup)
    paths.append(signup)

    print(f"📸 Generated {len(paths)} carousel slide(s) in {output_dir}")
    return paths
