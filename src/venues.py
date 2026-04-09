"""Venue metadata: neighborhood + Google Maps link.

Venue strings vary across scrapers (e.g., "BCC Eris Mainstage", "UCB Hell's
Kitchen", "The PIT Loft"), so we match by prefix/keyword rather than by
exact string.
"""

from __future__ import annotations

# Each entry: (match_keyword, neighborhood, google_maps_url)
# Order matters — first match wins, so put more specific prefixes first.
_VENUE_RULES: list[tuple[str, str, str]] = [
    # The PIT — 123 E 24th St, NoMad
    ("the pit", "NoMad",
     "https://www.google.com/maps/search/?api=1&query=The+PIT+123+E+24th+St+New+York+NY"),
    ("pit", "NoMad",
     "https://www.google.com/maps/search/?api=1&query=The+PIT+123+E+24th+St+New+York+NY"),

    # Magnet Theater — 254 W 29th St, Chelsea / Hell's Kitchen border
    ("magnet", "Chelsea",
     "https://www.google.com/maps/search/?api=1&query=Magnet+Theater+254+W+29th+St+New+York+NY"),

    # Brooklyn Comedy Collective — Eris venues, Bushwick
    ("bcc", "Bushwick",
     "https://www.google.com/maps/search/?api=1&query=Brooklyn+Comedy+Collective+Bushwick"),
    ("brooklyn comedy", "Bushwick",
     "https://www.google.com/maps/search/?api=1&query=Brooklyn+Comedy+Collective+Bushwick"),

    # UCB NY — Hell's Kitchen mainstage
    ("ucb", "Hell's Kitchen",
     "https://www.google.com/maps/search/?api=1&query=UCB+Comedy+New+York"),

    # Second City NY — Williamsburg
    ("second city", "Williamsburg",
     "https://www.google.com/maps/search/?api=1&query=Second+City+New+York+Williamsburg"),

    # Caveat — 21A Clinton St, Lower East Side
    ("caveat", "Lower East Side",
     "https://www.google.com/maps/search/?api=1&query=Caveat+21A+Clinton+St+New+York+NY"),

    # The Rat — Bushwick
    ("rat", "Bushwick",
     "https://www.google.com/maps/search/?api=1&query=The+Rat+NYC+Bushwick"),
]


def lookup(venue: str) -> tuple[str, str]:
    """Return (neighborhood, maps_url) for a venue string.

    Falls back to ("NYC", generic search URL) if no rule matches.
    """
    if not venue:
        return ("NYC", "https://www.google.com/maps/search/?api=1&query=New+York+NY")
    v = venue.lower()
    for keyword, neighborhood, maps_url in _VENUE_RULES:
        if keyword in v:
            return (neighborhood, maps_url)
    return ("NYC",
            f"https://www.google.com/maps/search/?api=1&query={venue.replace(' ', '+')}+New+York+NY")
