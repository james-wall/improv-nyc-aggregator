import re

# Patterns that indicate a class/student show.
# Order matters — checked top to bottom, first match wins.
_CLASS_SHOW_PATTERNS = [
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
]

_CLASS_SHOW_RE = re.compile('|'.join(_CLASS_SHOW_PATTERNS), re.IGNORECASE)


def is_class_show(title: str) -> bool:
    """Return True if the title looks like a class/student show."""
    return bool(_CLASS_SHOW_RE.search(title))
