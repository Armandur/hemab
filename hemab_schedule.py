#!/usr/bin/env python3
"""
Hämtar tömningsschema från HEMAB:s webbplats (Härnösand Energi & Miljö AB).

Flöde:
  1. Söksidan träffas med ?query=<gatunamn> och returnerar matchande gator
     med länkar till individuella gatusidor.
  2. Gatusidan hämtas och innehåller det faktiska tömningsschemat.

Användning:
    python hemab_schedule.py "Södra Strömsborgsgatan"
    python hemab_schedule.py "Storgatan"
    python hemab_schedule.py --url https://www.hemab.se/.../sundsgatan....html
"""

import sys
import re
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEMAB_BASE = "https://www.hemab.se"
SEARCH_URL = (
    f"{HEMAB_BASE}/atervinning/"
    "soksophamtningsdag.4.8575e6181a2a345d3ca8a6.html"
)
# Individuella gatusidor lever under denna sökväg
STREET_PATH_PREFIX = "/atervinning/soksophamtningsdag/gator/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Referer": HEMAB_BASE + "/",
}


def fetch_search_page(query: str, debug_file: str | None = None) -> str:
    """Hämtar söksidans HTML för given adress."""
    resp = requests.get(SEARCH_URL, params={"query": query}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    if debug_file:
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"[debug] HTML sparad till {debug_file!r} ({len(resp.text)} tecken)")
    return resp.text


def _find_street_links(html: str) -> list[dict]:
    """
    Letar efter <a>-taggar som pekar till individuella gatusidor.
    Returnerar lista av {"name": str, "url": str}.
    """
    soup = BeautifulSoup(html, "html.parser")
    streets = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if STREET_PATH_PREFIX in href:
            name = a.get_text(strip=True)
            url = urljoin(HEMAB_BASE, href)
            if name and url not in {s["url"] for s in streets}:
                streets.append({"name": name, "url": url})
    return streets


def fetch_street_schedule(url: str) -> dict:
    """
    Hämtar tömningsschemat från en individuell gatusida.

    Returnerar ett dict med gatunamn och tömningsinformation.
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return _parse_street_page(resp.text, url)


def _parse_street_page(html: str, source_url: str = "") -> dict:
    """Parsar en individuell gatusidas HTML och extraherar schemat."""
    soup = BeautifulSoup(html, "html.parser")

    result = {"url": source_url, "gatunamn": None, "schema": []}

    # Gatunamn — vanligtvis i h1 eller sidans titel
    h1 = soup.find("h1")
    if h1:
        result["gatunamn"] = h1.get_text(strip=True)

    # Tömningsinfo i tabeller
    for table in soup.find_all("table"):
        headers: list[str] = []
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            texts = [c.get_text(strip=True) for c in cells]
            if not texts:
                continue
            if all(c.name == "th" for c in cells):
                headers = texts
            else:
                entry = dict(zip(headers, texts)) if headers else {"kolumner": texts}
                result["schema"].append(entry)

    if result["schema"]:
        return result

    # Tömningsinfo i definitionslistor (<dl><dt>/<dd>)
    for dl in soup.find_all("dl"):
        terms = dl.find_all("dt")
        defs = dl.find_all("dd")
        for dt, dd in zip(terms, defs):
            result["schema"].append({
                dt.get_text(strip=True): dd.get_text(strip=True)
            })

    if result["schema"]:
        return result

    # Generell textsökning efter vecka/dag-mönster
    main = soup.find("main") or soup.find(id=re.compile(r"main|content", re.I))
    text = (main or soup).get_text(" ", strip=True)

    # Extrahera rader som nämner vecka, dag eller tömning
    schedule_lines = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"vecka|måndag|tisdag|onsdag|torsdag|fredag|tömning", line, re.I)
    ]
    if schedule_lines:
        result["schema"] = [{"info": line} for line in schedule_lines]
    else:
        result["schema"] = [{"råtext": text[:2000]}]

    return result


def get_schedule(address: str, debug_file: str | None = None) -> list[dict]:
    """
    Huvudfunktion: söker adress och returnerar tömningsschema.

    Strategi:
      1. Hämtar söksidan för adressen.
      2. Om sidan innehåller länkar till individuella gatusidor hämtas dessa.
      3. Annars parsas schemadata direkt ur söksidans HTML (inline-resultat).
    """
    html = fetch_search_page(address, debug_file=debug_file)

    streets = _find_street_links(html)
    if streets:
        schedules = []
        for street in streets:
            schedule = fetch_street_schedule(street["url"])
            if not schedule.get("gatunamn"):
                schedule["gatunamn"] = street["name"]
            schedules.append(schedule)
        return schedules

    # Resultaten visas inline på söksidan — parsa direkt
    schedule = _parse_street_page(html, source_url=SEARCH_URL + f"?query={address}")
    if not schedule.get("gatunamn"):
        schedule["gatunamn"] = address
    return [schedule] if schedule.get("schema") else []


def main():
    parser = argparse.ArgumentParser(description="Hämta HEMAB tömningsschema")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("address", nargs="?", help="Gatunamn att söka efter")
    group.add_argument("--url", help="Direkt URL till en HEMAB gatusida")
    parser.add_argument(
        "--debug",
        metavar="FIL",
        help="Spara rå-HTML från söksidan till angiven fil (t.ex. debug.html)",
    )
    args = parser.parse_args()

    try:
        if args.url:
            schedules = [fetch_street_schedule(args.url)]
        else:
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
        if s.get("url"):
            print(f"  URL: {s['url']}")
        for entry in s.get("schema", []):
            for k, v in entry.items():
                print(f"  {k}: {v}")
        print()


if __name__ == "__main__":
    main()
