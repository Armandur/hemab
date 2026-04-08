#!/usr/bin/env python3
"""
Hämtar tömningsschema från HEMAB:s webbplats.

Användning:
    python hemab_schedule.py "Södra Strömsborgsgatan"
    python hemab_schedule.py "Storgatan 5"
"""

import sys
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = (
    "https://www.hemab.se/atervinning/"
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
    "Referer": "https://www.hemab.se/",
}


def fetch_schedule(address: str) -> list[dict]:
    """
    Hämtar tömningsschema för given adress.

    Returnerar lista av poster med gatunamn och tömningsdagar.
    """
    resp = requests.get(
        BASE_URL,
        params={"query": address},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()

    return parse_schedule(resp.text)


def parse_schedule(html: str) -> list[dict]:
    """Parsar HTML-svar och extraherar tömningsdata."""
    soup = BeautifulSoup(html, "lxml")

    results = []

    # HEMAB verkar använda en tabell eller lista för resultaten.
    # Vi letar efter vanliga mönster: tabeller, listor med adress+veckodag-info.

    # Försök 1: leta efter tabeller
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        headers = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            texts = [c.get_text(strip=True) for c in cells]
            if not texts:
                continue
            if all(c.name == "th" for c in cells):
                headers = texts
            else:
                entry = dict(zip(headers, texts)) if headers else {"kolumner": texts}
                results.append(entry)

    if results:
        return results

    # Försök 2: leta efter listor / artiklar med adressinfo
    for item in soup.find_all(class_=re.compile(r"result|search|item|row|card", re.I)):
        text = item.get_text(" ", strip=True)
        if text:
            results.append({"text": text})

    if results:
        return results

    # Fallback: returnera hela sökresultat-sektionens text för felsökning
    main = soup.find("main") or soup.find(id=re.compile(r"main|content", re.I))
    if main:
        return [{"råtext": main.get_text(" ", strip=True)[:2000]}]

    return [{"råtext": soup.get_text(" ", strip=True)[:2000]}]


def main():
    address = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Södra Strömsborgsgatan"
    print(f"Söker tömningsschema för: {address!r}\n")

    try:
        results = fetch_schedule(address)
    except requests.HTTPError as e:
        print(f"HTTP-fel: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Nätverksfel: {e}")
        sys.exit(1)

    if not results:
        print("Inga resultat hittades.")
        return

    for i, entry in enumerate(results, 1):
        print(f"--- Resultat {i} ---")
        for key, val in entry.items():
            print(f"  {key}: {val}")
        print()


if __name__ == "__main__":
    main()
