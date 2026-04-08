#!/usr/bin/env python3
"""
Hämtar tömningsschema från HEMAB:s webbplats (Härnösand Energi & Miljö AB).

Söksidan returnerar resultat inline i HTML — det finns inga separata gatusidor.
Varje träff är ett <li class="sv-search-hit"> med gatunamn, veckodag och kärl/veckor.

Användning:
    python hemab_schedule.py "Södra Strömsborgsgatan"
    python hemab_schedule.py "Storgatan"
"""

import sys
import argparse
import requests
from bs4 import BeautifulSoup

HEMAB_BASE = "https://www.hemab.se"
SEARCH_URL = (
    f"{HEMAB_BASE}/atervinning/"
    "soksophamtningsdag.4.8575e6181a2a345d3ca8a6.html"
)

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


def _parse_search_hits(html: str) -> list[dict]:
    """
    Parsar söksidans inline-resultat.

    Varje <li class="sv-search-hit"> innehåller:
      <p class="c11967">   — gatunamn
      <p class="day">      — veckodag  (<strong>Veckodag</strong> Torsdag)
      <p class="bin1">     — kärl 1    (<strong>Kärl</strong> Fyrfackskärl 2)
      <p class="Week1">    — veckor 1  (<strong>Veckor</strong> Udda veckor: ...)
      <p class="Bin2">     — kärl 2    (<strong>Kärl</strong> Fyrfackskärl 1)
      <p class="Week2">    — veckor 2  (<strong>Veckor</strong> Udda veckor: ...)
      ... (fler kärl/veckor-par kan förekomma)
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for hit in soup.find_all("li", class_="sv-search-hit"):
        # Gatunamn
        name_tag = hit.find("p", class_="c11967")
        gatunamn = name_tag.get_text(strip=True) if name_tag else None

        # Veckodag
        day_tag = hit.find("p", class_="day")
        veckodag = None
        if day_tag:
            strong = day_tag.find("strong")
            if strong:
                strong.extract()
            veckodag = day_tag.get_text(strip=True)

        # Kärl/veckor-par: bin1/Week1, Bin2/Week2, ...
        karl_veckor = []
        for i in range(1, 10):
            # Klassen är "bin1" (gemen) för första, "Bin2" (versal) för övriga
            bin_class = f"bin{i}" if i == 1 else f"Bin{i}"
            week_class = f"Week{i}"

            bin_tag = hit.find("p", class_=bin_class)
            week_tag = hit.find("p", class_=week_class)

            if not bin_tag and not week_tag:
                break

            def extract_text(tag):
                if not tag:
                    return None
                strong = tag.find("strong")
                if strong:
                    strong.extract()
                return tag.get_text(strip=True)

            karl = extract_text(bin_tag)
            veckor = extract_text(week_tag)

            if karl or veckor:
                karl_veckor.append({"kärl": karl, "veckor": veckor})

        results.append({
            "gatunamn": gatunamn,
            "veckodag": veckodag,
            "schema": karl_veckor,
        })

    return results


def get_schedule(address: str, debug_file: str | None = None) -> list[dict]:
    """Söker efter adress och returnerar tömningsschema."""
    html = fetch_search_page(address, debug_file=debug_file)
    return _parse_search_hits(html)


def main():
    parser = argparse.ArgumentParser(description="Hämta HEMAB tömningsschema")
    parser.add_argument("address", help="Gatunamn att söka efter")
    parser.add_argument(
        "--debug",
        metavar="FIL",
        help="Spara rå-HTML från söksidan till angiven fil (t.ex. debug.html)",
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
