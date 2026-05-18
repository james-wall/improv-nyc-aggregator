#!/usr/bin/env python3
"""CLI for managing the performer registry.

Usage:
    # Add or update a performer
    python scripts/manage_performers.py add "Kate McKinnon" --ig katemckinnon --venue UCB

    # List all performers (optionally filtered by venue)
    python scripts/manage_performers.py list
    python scripts/manage_performers.py list --venue "Magnet"

    # Search by name, handle, or venue keyword
    python scripts/manage_performers.py search "magnet"

    # Show a single performer's full profile
    python scripts/manage_performers.py show "Kate McKinnon"

    # Link a performer to a specific show (by show URL)
    python scripts/manage_performers.py link "Kate McKinnon" https://... --role performer
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.store import performers as store
from src.store.db import _conn, init_db


def cmd_add(args):
    pid = store.upsert_performer(
        name=args.name,
        ig_handle=args.ig,
        twitter_handle=args.twitter,
        tiktok_handle=args.tiktok,
        website=args.website,
        bio=args.bio,
        home_venue=args.venue,
    )
    p = store.get_performer(args.name)
    print(f"✓ Saved performer #{pid}: {p['name']}")
    _print_performer(p)


def cmd_list(args):
    performers = store.list_performers(home_venue=args.venue)
    if not performers:
        print("No performers found.")
        return
    print(f"{'Name':<30} {'IG':<25} {'Venue':<25}")
    print("-" * 80)
    for p in performers:
        ig = f"@{p['ig_handle']}" if p.get("ig_handle") else "—"
        venue = p.get("home_venue") or "—"
        print(f"{p['name']:<30} {ig:<25} {venue:<25}")
    print(f"\n{len(performers)} performer(s)")


def cmd_search(args):
    results = store.search_performers(args.query)
    if not results:
        print(f"No performers matching '{args.query}'.")
        return
    for p in results:
        ig = f"@{p['ig_handle']}" if p.get("ig_handle") else "—"
        print(f"  {p['name']}  {ig}  {p.get('home_venue') or ''}")


def cmd_show(args):
    p = store.get_performer(args.name)
    if not p:
        print(f"Performer '{args.name}' not found.")
        sys.exit(1)
    _print_performer(p)

    # Show linked shows
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT s.title, s.venue, o.start_time, sp.role
            FROM show_performers sp
            JOIN shows s ON s.id = sp.show_id
            LEFT JOIN occurrences o ON o.show_id = s.id
            WHERE sp.performer_id = ?
            ORDER BY o.start_time DESC
            LIMIT 20
            """,
            (p["id"],),
        ).fetchall()
    if rows:
        print(f"\nLinked shows ({len(rows)}):")
        for r in rows:
            print(f"  {r['start_time'][:10] if r['start_time'] else '?'}  "
                  f"{r['venue']}  —  {r['title']}  [{r['role']}]")


def cmd_pending(args):
    """Show performers with auto-discovered handles waiting for verification."""
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT name, ig_handle, home_venue FROM performers
            WHERE ig_confidence = 'auto'
            ORDER BY name
            """
        ).fetchall()
    if not rows:
        print("No performers pending verification.")
        return
    print(f"{'Name':<30} {'Auto-discovered IG':<28} {'Venue'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['name']:<30} @{r['ig_handle']:<27} {r['home_venue'] or '—'}")
    print(f"\n{len(rows)} pending. Use 'verify' or 'reject' to action them.")


def cmd_verify(args):
    """Mark an auto-discovered IG handle as verified (or supply a correction)."""
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM performers WHERE name = ? COLLATE NOCASE", (args.name,)
        ).fetchone()
    if not row:
        print(f"Performer '{args.name}' not found.")
        sys.exit(1)

    new_handle = args.ig or row["ig_handle"]
    with _conn() as conn:
        conn.execute(
            "UPDATE performers SET ig_handle = ?, ig_confidence = 'verified', updated_at = datetime('now') WHERE id = ?",
            (new_handle, row["id"]),
        )
    print(f"✓ {args.name} → @{new_handle} marked as verified")


def cmd_reject(args):
    """Clear an auto-discovered handle and mark the performer as unfound."""
    init_db()
    with _conn() as conn:
        conn.execute(
            "UPDATE performers SET ig_handle = NULL, ig_confidence = 'unfound', updated_at = datetime('now') WHERE name = ? COLLATE NOCASE",
            (args.name,),
        )
    print(f"✓ {args.name} → handle cleared, marked unfound")


def cmd_link(args):
    p = store.get_performer(args.name)
    if not p:
        print(f"Performer '{args.name}' not found. Add them first with 'add'.")
        sys.exit(1)
    from src.store.db import get_show
    show = get_show(args.url)
    if not show:
        print(f"Show URL not found in database: {args.url}")
        sys.exit(1)
    store.link_performer_to_show(show["id"], p["id"], role=args.role)
    print(f"✓ Linked {p['name']} → '{show['title']}' as {args.role}")


def _print_performer(p: dict):
    fields = [
        ("Instagram",  f"@{p['ig_handle']}"      if p.get("ig_handle")      else "—"),
        ("Twitter",    f"@{p['twitter_handle']}"  if p.get("twitter_handle") else "—"),
        ("TikTok",     f"@{p['tiktok_handle']}"   if p.get("tiktok_handle")  else "—"),
        ("Website",    p.get("website")            or "—"),
        ("Home venue", p.get("home_venue")         or "—"),
        ("Bio",        p.get("bio")                or "—"),
    ]
    print()
    for label, val in fields:
        print(f"  {label:<12} {val}")


def main():
    parser = argparse.ArgumentParser(description="Manage the Our Scene performer registry")
    sub = parser.add_subparsers(dest="cmd")

    # add
    p_add = sub.add_parser("add", help="Add or update a performer")
    p_add.add_argument("name")
    p_add.add_argument("--ig",      dest="ig",      default=None, help="Instagram handle (no @)")
    p_add.add_argument("--twitter", dest="twitter", default=None, help="Twitter/X handle (no @)")
    p_add.add_argument("--tiktok",  dest="tiktok",  default=None, help="TikTok handle (no @)")
    p_add.add_argument("--website", dest="website", default=None)
    p_add.add_argument("--bio",     dest="bio",     default=None)
    p_add.add_argument("--venue",   dest="venue",   default=None, help="Primary home venue")

    # list
    p_list = sub.add_parser("list", help="List all performers")
    p_list.add_argument("--venue", default=None)

    # search
    p_search = sub.add_parser("search", help="Search performers")
    p_search.add_argument("query")

    # show
    p_show = sub.add_parser("show", help="Show a performer's full profile")
    p_show.add_argument("name")

    # link
    p_link = sub.add_parser("link", help="Link a performer to a show URL")
    p_link.add_argument("name")
    p_link.add_argument("url")
    p_link.add_argument("--role", default="performer")

    # pending
    sub.add_parser("pending", help="Show auto-discovered handles waiting for review")

    # verify
    p_verify = sub.add_parser("verify", help="Confirm an auto-discovered IG handle")
    p_verify.add_argument("name")
    p_verify.add_argument("--ig", default=None, help="Override handle if the auto-discovered one is wrong")

    # reject
    p_reject = sub.add_parser("reject", help="Clear a wrong auto-discovered handle")
    p_reject.add_argument("name")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "add": cmd_add, "list": cmd_list, "search": cmd_search,
        "show": cmd_show, "link": cmd_link,
        "pending": cmd_pending, "verify": cmd_verify, "reject": cmd_reject,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
