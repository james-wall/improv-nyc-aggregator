#!/usr/bin/env python3
"""Refresh the long-lived Instagram access token and print the new one to stdout.

Instagram "Instagram Login" long-lived tokens last 60 days; calling
refresh_access_token (on a token that is >24h old and not yet expired) returns a
fresh token good for another 60 days. Run on a schedule so the token never lapses.

Used by .github/workflows/refresh-instagram-token.yml. Prints ONLY the new token
to stdout (so the workflow can capture it without it leaking into logs); all
diagnostics go to stderr.
"""

import os
import sys

import requests

_DEFAULT_API_VERSION = "v25.0"  # refresh endpoint is unversioned, kept for parity


def main() -> None:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        print("INSTAGRAM_ACCESS_TOKEN is not set", file=sys.stderr)
        sys.exit(1)

    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=30,
    )
    if not resp.ok:
        print(f"Refresh failed {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    new_token = data.get("access_token")
    if not new_token:
        print(f"No access_token in refresh response: {data}", file=sys.stderr)
        sys.exit(1)

    days = int(data.get("expires_in", 0)) // 86400
    print(f"Refreshed OK — new token valid ~{days} days", file=sys.stderr)
    # ONLY the token on stdout, so `NEW_TOKEN=$(python ...)` captures just this.
    print(new_token)


if __name__ == "__main__":
    main()
