from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Event:
    title: str
    venue: str
    start_time: datetime | None
    description: str
    url: str
    source: str
    time_known: bool = True
    is_class_show: bool = False
    show_format: str | None = None  # "class_show", "jam", "open_mic", or None
    price: str | None = None
