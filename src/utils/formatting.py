from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Show format detection
# ---------------------------------------------------------------------------

_FORMAT_RULES: list[tuple[str, re.Pattern]] = [
    # --- Class / student shows ---
    ("class_show", re.compile(
        r'|'.join([
            r'\bclass show\b',
            r'\bgrad show\b',
            r'\bgrad revue\b',
            r'\blevel \d+ improv\b',
            r'\blevel \d+ stand[- ]?up\b',
            r'\blevel \d+ sketch\b',
            r'\bimprov level \w+\b',
            r'\bstorytelling level \w+\b',
            r'\bwriting level \w+\b',
            r'\bconservatory \d+\b',
            r'\bimprov \d+ show\b',
            r'\bimprov \d+ &\b',
            r'\bwriting \d+ show\b',
            r'\bacting \d+ show\b',
            r'\bstand up \d+ show\b',
        ]),
        re.IGNORECASE,
    )),

    # --- Jams ---
    ("jam", re.compile(
        r'|'.join([
            r'\bimprov jam\b',
            r'\bthe \w* ?jam\b',
            r'\bjam[!.]?\s*$',            # title ending in "jam", "jam!", "jam."
            r'\bafters jam\b',             # "UCBLK Afters Jam!"
            r'\bfeel-?good.*jam\b',
            r'\bin n.? out.*jam\b',
        ]),
        re.IGNORECASE,
    )),

    # --- Open mics ---
    ("open_mic", re.compile(
        r'|'.join([
            r'\bopen mic\b',
            r'\bopen ass mic\b',           # "BCC Open Ass Mic"
            r'\bthe secret mic\b',
            r'\bshow mic\b',               # "The Wednesday Show MIC"
            r'\bmic\s*$',                  # title ending in "mic" or "MIC"
        ]),
        re.IGNORECASE,
    )),
]


def detect_show_format(title: str) -> str | None:
    """Return the show format tag, or None for a regular show.

    Possible return values (extensible):
    - "class_show" — class/student showcases
    - "jam" — improv jams and drop-in jams
    - "open_mic" — open mics and similar sign-up shows
    - None — regular ticketed show
    """
    for tag, pattern in _FORMAT_RULES:
        if pattern.search(title):
            return tag
    return None


# Backwards-compatible alias
def is_class_show(title: str) -> bool:
    """Return True if the title looks like a class/student show."""
    return detect_show_format(title) == "class_show"


# ---------------------------------------------------------------------------
# Title normalization
# ---------------------------------------------------------------------------

# Regex to match emoji and other symbol characters
_EMOJI_RE = re.compile(
    r'[\U0001F300-\U0001FAFF'   # Misc symbols, emoticons, dingbats, etc.
    r'\U00002702-\U000027B0'    # Dingbats
    r'\U0000FE00-\U0000FE0F'    # Variation selectors
    r'\U0000200D'               # Zero-width joiner
    r'\U000020E3'               # Combining enclosing keycap
    r'\U00002600-\U000026FF'    # Misc symbols
    r'\U0000231A-\U0000231B'    # Watch, hourglass
    r'\U00002934-\U00002935'    # Arrows
    r'\U000025AA-\U000025FE'    # Geometric shapes
    r'\U00002B05-\U00002B55'    # Arrows, symbols
    r']+',
    re.UNICODE,
)

# Words that should stay lowercase in title case (unless first/last)
_TITLE_SMALL_WORDS = {
    'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
    'at', 'by', 'in', 'of', 'on', 'to', 'up', 'vs', 'vs.',
}


def normalize_title(title: str) -> str:
    """Normalize a show title for consistent display.

    - Strips emoji
    - Converts ALL CAPS to title case (preserves mixed-case titles)
    - Cleans up extra whitespace and dashes
    - Preserves intentional abbreviations/acronyms (e.g., "NYC", "SNL", "ASL")
    """
    if not title:
        return title

    # Strip emoji
    text = _EMOJI_RE.sub(' ', title)

    # Clean up whitespace (multiple spaces, leading/trailing)
    text = re.sub(r'\s+', ' ', text).strip()

    # Clean up orphaned punctuation from emoji removal (e.g., "🎭 TITLE 🎭" -> "TITLE")
    text = re.sub(r'^\s*[–—-]\s*', '', text)
    text = re.sub(r'\s*[–—-]\s*$', '', text)
    text = text.strip()

    # Only convert case if the title is mostly uppercase (ALL CAPS)
    # Heuristic: if >70% of alpha chars are uppercase, it's ALL CAPS
    alpha_chars = [c for c in text if c.isalpha()]
    if alpha_chars:
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.7:
            text = _smart_title_case(text)

    return text


# Known acronyms / brand names to preserve as-is when found in ALL CAPS titles
_KNOWN_ACRONYMS = {
    'NYC', 'SNL', 'ASL', 'UCB', 'BCC', 'PIT', 'UCBLK', 'TBD', 'DJ', 'MC',
    'LGBTQ', 'LGBTQ+', 'TV', 'NYU', 'HBO', 'NBC', 'CBS', 'ABC', 'PBS',
    'ASSSSCAT', 'ASSSSKETCH', 'TF', 'II', 'III', 'IV', 'NY', 'LA',
}


def _smart_title_case(text: str) -> str:
    """Convert to title case while preserving known acronyms.

    Known acronyms are kept uppercase. Small words (a, the, of, etc.)
    are lowercased unless first/last.
    """
    words = text.split()
    result = []
    for i, word in enumerate(words):
        # Strip punctuation for analysis, preserve it in output
        stripped = word.strip('.,!?:;()"-–—…')

        # Preserve known acronyms
        if stripped.upper() in _KNOWN_ACRONYMS:
            result.append(word.upper() if stripped.isupper() else word)
        # Small words lowercase (unless first or last)
        elif stripped.lower() in _TITLE_SMALL_WORDS and i != 0 and i != len(words) - 1:
            result.append(word.lower())
        else:
            result.append(word.capitalize())

    return ' '.join(result)
