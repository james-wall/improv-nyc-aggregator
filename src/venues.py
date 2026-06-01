"""Venue metadata: neighborhood, Google Maps link, and Instagram handle.

Venue strings vary across scrapers (e.g., "BCC Eris Mainstage", "UCB Hell's
Kitchen", "The PIT Loft"), so we match by prefix/keyword rather than by
exact string.
"""

from __future__ import annotations

# Each entry: (match_keyword, neighborhood, google_maps_url, ig_handle)
# ig_handle is without the @ sign. Empty string means unknown/unverified.
# Order matters — first match wins, so put more specific prefixes first.
_VENUE_RULES: list[tuple[str, str, str, str]] = [
    # The PIT — 123 E 24th St, Flatiron
    ("the pit", "Flatiron",
     "https://www.google.com/maps/search/?api=1&query=The+PIT+123+E+24th+St+New+York+NY",
     "thepitnyc"),
    ("pit", "Flatiron",
     "https://www.google.com/maps/search/?api=1&query=The+PIT+123+E+24th+St+New+York+NY",
     "thepitnyc"),

    # Magnet Theater — 254 W 29th St, Chelsea
    ("magnet", "Chelsea",
     "https://www.google.com/maps/search/?api=1&query=Magnet+Theater+254+W+29th+St+New+York+NY",
     "magnettheater"),

    # Brooklyn Comedy Collective — Eris venues, Bushwick
    ("bcc", "Bushwick",
     "https://www.google.com/maps/search/?api=1&query=Brooklyn+Comedy+Collective+Bushwick",
     "brooklyncomedycollective"),
    ("brooklyn comedy", "Bushwick",
     "https://www.google.com/maps/search/?api=1&query=Brooklyn+Comedy+Collective+Bushwick",
     "brooklyncomedycollective"),

    # UCB NY — 242 E 14th St, East Village
    ("ucb", "East Village",
     "https://www.google.com/maps/search/?api=1&query=UCB+Comedy+242+E+14th+St+New+York+NY",
     "ucbcomedy"),

    # Second City NY — Williamsburg
    ("second city", "Williamsburg",
     "https://www.google.com/maps/search/?api=1&query=Second+City+New+York+Williamsburg",
     "secondcityny"),

    # Caveat — 21A Clinton St, Lower East Side
    ("caveat", "Lower East Side",
     "https://www.google.com/maps/search/?api=1&query=Caveat+21A+Clinton+St+New+York+NY",
     "caveat_nyc"),

    # The Rat — 68 Jay St, Downtown Brooklyn
    ("rat", "Downtown Brooklyn",
     "https://www.google.com/maps/search/?api=1&query=The+Rat+68+Jay+St+Brooklyn+NY",
     "theratnyc"),
]


def lookup(venue: str) -> tuple[str, str]:
    """Return (neighborhood, maps_url) for a venue string."""
    if not venue:
        return ("NYC", "https://www.google.com/maps/search/?api=1&query=New+York+NY")
    v = venue.lower()
    for keyword, neighborhood, maps_url, _ig in _VENUE_RULES:
        if keyword in v:
            return (neighborhood, maps_url)
    return ("NYC",
            f"https://www.google.com/maps/search/?api=1&query={venue.replace(' ', '+')}+New+York+NY")


def ig_handle(venue: str) -> str | None:
    """Return the Instagram handle (without @) for a venue, or None if unknown."""
    if not venue:
        return None
    v = venue.lower()
    for keyword, _nb, _maps, handle in _VENUE_RULES:
        if keyword in v:
            return handle or None
    return None
