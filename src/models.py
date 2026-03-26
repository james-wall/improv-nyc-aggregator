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
