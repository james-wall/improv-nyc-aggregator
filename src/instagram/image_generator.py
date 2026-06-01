"""Generate Instagram carousel slides from curated newsletter data.

Clean, readable, information-dense — inspired by weekly-listing accounts like
@thirstygallerina: a light background, one compact row per show, and brand
colour as an accent rather than a full dark canvas.

Slides: top-picks lead  →  one slide per day (every show, as a scannable list)  →  signup CTA.
All slides are 1080x1080.

NOTE: the rendering pipeline (Pillow + Liberation/Arial) cannot draw colour
emoji — they come out as tofu boxes — so visual cues use shapes/text that always
render: a drawn gold ★ for top picks and a green "FREE" tag.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1080

# ── Palette — clean light base, burgundy + gold brand accents ──────────────────
BG       = (250, 247, 241)   # warm off-white
INK      = (30,  24,  28)    # near-black (titles)
INK_DIM  = (122, 112, 118)   # secondary text (venue / neighborhood / blurb)
BURGUNDY = (139,  0,   0)    # brand — day headers, show times
GOLD     = (173, 134,  18)   # deeper gold, legible on light — accents, ★
GREEN    = (28,  126,  64)   # "FREE" tag
LINE     = (228, 221, 212)   # hairline separators
WHITE    = (255, 255, 255)

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


def _line_h(font):
    """Stable line height independent of the specific glyphs drawn."""
    asc, desc = font.getmetrics()
    return asc + desc


def _trunc(draw, text, font, max_px):
    if _tw(draw, text, font) <= max_px:
        return text
    while len(text) > 1 and _tw(draw, text + "…", font) > max_px:
        text = text[:-1]
    return text.rstrip() + "…"


def _center(draw, text, y, font, fill):
    draw.text(((W - _tw(draw, text, font)) // 2, y), text, font=font, fill=fill)


def _save_jpeg(img, output_path: str) -> None:
    """JPEG is the only format Instagram's publishing API accepts. subsampling=0
    (4:4:4) keeps text/edges crisp on these flat-colour graphics."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "JPEG", quality=95, subsampling=0)


def _star(draw, cx, cy, r, fill):
    """Draw a filled 5-point star centred at (cx, cy) — renders reliably (unlike ⭐)."""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def _free_tag(draw, x, y, font) -> int:
    """Small green FREE pill; returns its width."""
    txt = "FREE"
    tw = _tw(draw, txt, font)
    h = _line_h(font)
    pad_x, pad_y = 9, 3
    draw.rounded_rectangle([x, y, x + tw + 2 * pad_x, y + h + 2 * pad_y],
                           radius=7, fill=GREEN)
    draw.text((x + pad_x, y + pad_y), txt, font=font, fill=WHITE)
    return tw + 2 * pad_x


def _brandmark(draw):
    """Subtle footer: thin gold rule + @ourscenenyc."""
    f = _font(30, bold=True)
    draw.rectangle([0, H - 70, W, H - 68], fill=GOLD)
    _center(draw, "@ourscenenyc", H - 52, f, BURGUNDY)


def _is_free(show) -> bool:
    return "free" in (str(show.get("price") or "") + " " + str(show.get("title") or "")).lower()


# ── Top-picks lead slide (one standout per night) ──────────────────────────────

def generate_top_picks_slide(curated: dict, date_range: str, output_path: str) -> str:
    """Lead slide: the single best pick for each night + a swipe prompt.

    Content-first hook: immediate curated value, and a clear reason to swipe
    through the per-night full lineups.
    """
    from src.venues import lookup as venue_lookup

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    PAD = 58

    f_h = _font(50, bold=True)
    y = 66
    draw.text((PAD, y), "THIS WEEK'S TOP PICKS", font=f_h, fill=BURGUNDY)
    y += _line_h(f_h) + 4
    f_sub = _font(26)
    draw.text((PAD, y), f"One standout each night  ·  {date_range}", font=f_sub, fill=INK_DIM)
    y += _line_h(f_sub) + 14
    draw.rectangle([PAD, y, W - PAD, y + 5], fill=GOLD)
    y += 16

    days = [d for d in (curated.get("days") or []) if (d.get("shows") or [])]

    swipe_top = H - 166
    band_top = y
    band_h = swipe_top - band_top
    n = max(1, len(days))
    row_h = band_h / n

    f_day = _font(27, bold=True)
    f_title = _font(31, bold=True)
    f_meta = _font(24)
    title_x = PAD + 98

    for i, d in enumerate(days):
        shows = d.get("shows") or []
        pick = next((s for s in shows if s.get("starred")), shows[0])
        day_ab = (d.get("label") or "").split(",")[0].strip()[:3].upper()
        title = (pick.get("title") or "").strip()
        venue = (pick.get("venue") or "").strip()
        time_s = (pick.get("time") or "").strip()
        nb, _ = venue_lookup(venue)

        row_y = band_top + i * row_h
        content_h = _line_h(f_title) + _line_h(f_meta) + 4
        cy = int(row_y + max(0, (row_h - content_h) / 2))

        draw.text((PAD, cy + 2), day_ab, font=f_day, fill=BURGUNDY)
        _star(draw, title_x + 9, cy + _line_h(f_title) // 2, 12, GOLD)
        tx = title_x + 28
        draw.text((tx, cy), _trunc(draw, title, f_title, W - PAD - tx), font=f_title, fill=INK)

        meta = time_s
        if venue:
            meta += f"  ·  {venue}"
        if nb and nb != "NYC":
            meta += f"  ·  {nb}"
        draw.text((title_x, cy + _line_h(f_title) + 4),
                  _trunc(draw, meta, f_meta, W - PAD - title_x), font=f_meta, fill=INK_DIM)

        if i < n - 1:
            ly = int(band_top + (i + 1) * row_h) - 2
            draw.rectangle([PAD, ly, W - PAD, ly + 1], fill=LINE)

    draw.rectangle([PAD, swipe_top, W - PAD, swipe_top + 2], fill=GOLD)
    _center(draw, "Swipe for every night's full lineup  →",
            swipe_top + 22, _font(32, bold=True), BURGUNDY)

    _brandmark(draw)
    _save_jpeg(img, output_path)
    return output_path


# ── Day slide ─────────────────────────────────────────────────────────────────

def generate_day_slide(day: dict, output_path: str) -> str:
    from src.venues import lookup as venue_lookup

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    PAD = 60
    label = (day.get("label") or "").strip()
    shows = list(day.get("shows") or [])

    # Header
    f_day = _font(52, bold=True)
    hdr_y = 60
    draw.text((PAD, hdr_y), label.upper(), font=f_day, fill=BURGUNDY)
    rule_y = hdr_y + _line_h(f_day) + 12
    draw.rectangle([PAD, rule_y, W - PAD, rule_y + 5], fill=GOLD)
    content_top = rule_y + 30

    brandmark_top = H - 70

    if not shows:
        draw.text((PAD, content_top),
                  "No standout shows tonight — check the venues directly.",
                  font=_font(28), fill=INK_DIM)
        _brandmark(draw)
        _save_jpeg(img, output_path)
        return output_path

    # Density settings
    MAX = 11
    overflow = max(0, len(shows) - MAX)
    shows = shows[:MAX]
    n = len(shows)
    with_blurb = n <= 6

    f_time = _font(29, bold=True)
    f_title = _font(33, bold=True)
    f_meta = _font(25)
    f_blurb = _font(24)
    f_free = _font(20, bold=True)

    inner_w = W - 2 * PAD
    gap = 20 if n <= 7 else 13

    # Measure total content height so we can vertically centre on light nights
    def _row_h(s):
        h = _line_h(f_title) + 4 + _line_h(f_meta) + 4
        if with_blurb and (s.get("details") or "").strip():
            h += _line_h(f_blurb) + 4
        return h

    overflow_band = 36 if overflow else 0
    separator_h = gap + 1  # 1px line + gap split equally above/below
    content_h = (
        sum(_row_h(s) for s in shows)
        + separator_h * (n - 1)
        + overflow_band
    )

    available = brandmark_top - content_top
    # Vertical centre only when content is notably shorter than available space
    if content_h < available - 30:
        y = content_top + (available - content_h) // 2
    else:
        y = content_top

    for i, s in enumerate(shows):
        time_s = (s.get("time") or "TBA").strip()
        title = (s.get("title") or "").strip()
        venue = (s.get("venue") or "").strip()
        details = (s.get("details") or "").strip()
        starred = bool(s.get("starred"))
        nb, _ = venue_lookup(venue)

        # Line 1: time (burgundy) + ★ + title (ink)
        draw.text((PAD, y + 2), time_s, font=f_time, fill=BURGUNDY)
        x = PAD + _tw(draw, time_s, f_time) + 18
        if starred:
            _star(draw, x + 11, y + _line_h(f_title) // 2, 13, GOLD)
            x += 32
        draw.text((x, y), _trunc(draw, title, f_title, W - PAD - x), font=f_title, fill=INK)
        y += _line_h(f_title) + 4

        # Line 2: venue · neighborhood  (+ FREE tag)
        meta = venue if venue else ""
        if nb and nb != "NYC":
            meta = f"{meta}  ·  {nb}" if meta else nb
        reserve = 64 if _is_free(s) else 0
        draw.text((PAD, y), _trunc(draw, meta, f_meta, inner_w - reserve),
                  font=f_meta, fill=INK_DIM)
        if _is_free(s):
            _free_tag(draw,
                      PAD + _tw(draw, _trunc(draw, meta, f_meta, inner_w - reserve), f_meta) + 14,
                      y - 1, f_free)
        y += _line_h(f_meta) + 4

        # Line 3: short blurb (light nights only)
        if with_blurb and details:
            draw.text((PAD, y), _trunc(draw, details, f_blurb, inner_w),
                      font=f_blurb, fill=INK_DIM)
            y += _line_h(f_blurb) + 4

        # Hairline separator
        if i < n - 1:
            y += gap // 2
            draw.rectangle([PAD, y, W - PAD, y + 1], fill=LINE)
            y += gap // 2 + 1

    if overflow:
        draw.text((PAD, brandmark_top - 42),
                  f"+{overflow} more tonight — full lineup in the newsletter",
                  font=_font(23, bold=True), fill=GOLD)

    _brandmark(draw)
    _save_jpeg(img, output_path)
    return output_path


# ── Signup CTA slide ────────────────────────────────────────────────────────────

def generate_signup_slide(output_path: str) -> str:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    _center(draw, "Want the full lineup", 180, _font(70, bold=True), BURGUNDY)
    _center(draw, "every week?", 262, _font(70, bold=True), BURGUNDY)

    draw.rectangle([W // 2 - 160, 372, W // 2 + 160, 376], fill=GOLD)

    _center(draw, "Every show, every night —", 420, _font(36), INK)
    _center(draw, "descriptions, times, the works —", 466, _font(36), INK)
    _center(draw, "straight to your inbox.", 512, _font(36), INK)

    cta_y = 600
    draw.rounded_rectangle([140, cta_y, W - 140, cta_y + 84], radius=42, fill=BURGUNDY)
    _center(draw, "Link in bio to subscribe", cta_y + 22, _font(38, bold=True), WHITE)

    _center(draw, "Free  ·  Weekly  ·  No spam", 730, _font(30, bold=True), GOLD)

    draw.rectangle([W // 2 - 220, 800, W // 2 + 220, 801], fill=LINE)
    _center(draw, "Running a show worth seeing?", 826, _font(28), INK_DIM)
    _center(draw, "DM us or reply to any newsletter", 866, _font(28), INK_DIM)

    _brandmark(draw)
    _save_jpeg(img, output_path)
    return output_path


# ── Carousel entry point ──────────────────────────────────────────────────────

def generate_carousel(curated: dict, date_range: str, output_dir: str) -> list[str]:
    """Generate all carousel slides. Returns file paths in order:
    top-picks lead → one per day → signup CTA. Up to 10 slides (1 + 7 days + 1 = 9)."""
    os.makedirs(output_dir, exist_ok=True)
    paths = []

    lead = os.path.join(output_dir, "00_picks.jpg")
    generate_top_picks_slide(curated, date_range, lead)
    paths.append(lead)

    for i, day in enumerate(curated.get("days") or [], start=1):
        date_iso = day.get("date_iso", f"day{i:02d}")
        slide_path = os.path.join(output_dir, f"{i:02d}_{date_iso}.jpg")
        generate_day_slide(day, slide_path)
        paths.append(slide_path)

    signup = os.path.join(output_dir, "99_signup.jpg")
    generate_signup_slide(signup)
    paths.append(signup)

    print(f"📸 Generated {len(paths)} carousel slide(s) in {output_dir}")
    return paths
