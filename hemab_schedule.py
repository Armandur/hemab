#!/usr/bin/env python3
"""
Hämtar tömningsschema från HEMAB:s webbplats (Härnösand Energi & Miljö AB).

Användning:
    python hemab_schedule.py "Södra Strömsborgsgatan"
    python hemab_schedule.py "Storgatan"
    python hemab_schedule.py "Södra Strömsborgsgatan" --debug raw.html
"""

import sys
import argparse
import requests
from hemab_api import get_schedule


def main():
    parser = argparse.ArgumentParser(description="Hämta HEMAB tömningsschema")
    parser.add_argument("address", help="Gatunamn att söka efter (del av namn fungerar)")
    parser.add_argument(
        "--debug",
        metavar="FIL",
        help="Spara rå-HTML från söksidan till angiven fil",
    )
    args = parser.parse_args()

    try:
        print(f"Söker: {args.address!r}\n")
        schedules = get_schedule(args.address, debug_file=args.debug)
    except requests.HTTPError as e:
        print(f"HTTP-fel: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Nätverksfel: {e}", file=sys.stderr)
        sys.exit(1)

    if not schedules:
        print("Inga gator hittades.")
        return

    for s in schedules:
        print(f"=== {s.get('gatunamn') or 'Okänd gata'} ===")
        if s.get("veckodag"):
            print(f"  Veckodag: {s['veckodag']}")
        for entry in s.get("schema", []):
            print(f"  Kärl:   {entry.get('kärl')}")
            print(f"  Veckor: {entry.get('veckor')}")
        print()


if __name__ == "__main__":
    main()
