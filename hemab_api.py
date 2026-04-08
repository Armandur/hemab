"""
HEMAB API – hämtning och parsning av tömningsschema.

Delas av CLI (hemab_schedule.py), ICS-tjänsten (app.py) och
Home Assistant-integrationen (custom_components/hemab/).
"""

import re
import datetime
import requests
from bs4 import BeautifulSoup

HEMAB_BASE = "https://www.hemab.se"
AUTOCOMPLETE_URL = f"{HEMAB_BASE}/4.8575e6181a2a345d3ca8a6/12.8575e6181a2a345d3cb61f.json"
SEARCH_URL = (
    f"{HEMAB_BASE}/atervinning/"
    "soksophamtningsdag.4.8575e6181a2a345d3ca8a6.html"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) "
        "Gecko/20100101 Firefox/149.0"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"{HEMAB_BASE}/atervinning/soksophamtningsdag.4.8575e6181a2a345d3ca8a6.html",
}

# Fraktioner per kärltyp
KÄRL_INNEHÅLL: dict[str, list[str]] = {
    "Fyrfackskärl 1": ["Plastförpackningar", "Restavfall", "Ofärgat glas", "Metallförpackningar"],
    "Fyrfackskärl 2": ["Matavfall", "Pappersförpackningar", "Färgat glas", "Tidningar"],
}

VECKODAGAR: dict[str, int] = {
    "måndag": 0,
    "tisdag": 1,
    "onsdag": 2,
    "torsdag": 3,
    "fredag": 4,
    "lördag": 5,
    "söndag": 6,
}


# ---------------------------------------------------------------------------
# API-anrop
# ---------------------------------------------------------------------------

def autocomplete(term: str) -> list[str]:
    """Returnerar lista av exakta gatunamn som matchar söktermen."""
    resp = requests.get(
        AUTOCOMPLETE_URL,
        params={"state": "autoComplete", "term": term},
        headers={**HEADERS, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_schedule_html(exact_name: str, debug_file: str | None = None) -> str:
    """Hämtar söksidans HTML för ett exakt gatunamn."""
    resp = requests.get(
        SEARCH_URL,
        params={"query": exact_name},
        headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        timeout=15,
    )
    resp.raise_for_status()
    if debug_file:
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(resp.text)
    return resp.text


def _parse_search_hits(html: str) -> list[dict]:
    """
    Parsar söksidans inline-resultat.

    Varje <li class="sv-search-hit"> innehåller:
      <p class="c11967">   — gatunamn
      <p class="day">      — veckodag
      <p class="bin1">     — kärl 1
      <p class="Week1">    — veckor 1
      <p class="Bin2">     — kärl 2
      <p class="Week2">    — veckor 2
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for hit in soup.find_all("li", class_="sv-search-hit"):
        name_tag = hit.find("p", class_="c11967")
        gatunamn = name_tag.get_text(strip=True) if name_tag else None

        day_tag = hit.find("p", class_="day")
        veckodag = None
        if day_tag:
            strong = day_tag.find("strong")
            if strong:
                strong.extract()
            veckodag = day_tag.get_text(strip=True)

        def extract_text(tag):
            if not tag:
                return None
            strong = tag.find("strong")
            if strong:
                strong.extract()
            return tag.get_text(strip=True)

        karl_veckor = []
        for i in range(1, 10):
            bin_class = f"bin{i}" if i == 1 else f"Bin{i}"
            bin_tag = hit.find("p", class_=bin_class)
            week_tag = hit.find("p", class_=f"Week{i}")
            if not bin_tag and not week_tag:
                break
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
    """
    Söker efter adress och returnerar tömningsschema.

    Flöde:
      1. Autokomplett-API:et används för att hitta exakta gatunamn.
      2a. Exakt en träff → hämta HTML för det exakta namnet.
      2b. Flera träffar → ett HTML-anrop returnerar alla träffar inline.
    """
    matches = autocomplete(address)
    if not matches:
        return []

    if len(matches) == 1:
        html = _fetch_schedule_html(matches[0], debug_file=debug_file)
        return _parse_search_hits(html)

    html = _fetch_schedule_html(address, debug_file=debug_file)
    hits = _parse_search_hits(html)

    match_set = {m.lower() for m in matches}
    return [h for h in hits if (h.get("gatunamn") or "").lower() in match_set]


# ---------------------------------------------------------------------------
# Datumberäkning
# ---------------------------------------------------------------------------

def parse_veckor(veckor_str: str) -> list[int]:
    """Extraherar veckonummer ur en sträng som 'Udda veckor: 1, 3, 5, ...'"""
    return [int(m) for m in re.findall(r"\d+", veckor_str or "")]


def vecka_till_datum(år: int, vecka: int, veckodag: str) -> datetime.date:
    """Omvandlar ISO-vecka + veckodag till ett datum."""
    dag_offset = VECKODAGAR[veckodag.lower()]
    return datetime.date.fromisocalendar(år, vecka, dag_offset + 1)


def alla_datum(veckor_str: str, veckodag: str, år: int | None = None) -> list[datetime.date]:
    """Returnerar alla hämtningsdatum för angivna veckor och veckodag."""
    if not veckodag or veckodag.lower() not in VECKODAGAR:
        return []
    if år is None:
        år = datetime.date.today().year
    result = []
    for v in sorted(parse_veckor(veckor_str)):
        try:
            result.append(vecka_till_datum(år, v, veckodag))
        except ValueError:
            pass
    return result


def nästa_hämtning(veckor_str: str, veckodag: str) -> datetime.date | None:
    """Returnerar nästa hämtningsdatum från och med idag."""
    idag = datetime.date.today()
    år = idag.isocalendar()[0]
    for datum in alla_datum(veckor_str, veckodag, år):
        if datum >= idag:
            return datum
    # Inga fler hämtningar i år — ta första veckan nästa år
    kommande = alla_datum(veckor_str, veckodag, år + 1)
    return kommande[0] if kommande else None
