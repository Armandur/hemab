# Plan: HEMAB Home Assistant-integration

## Mål

En `custom_component` för Home Assistant som hämtar tömningsschema från HEMAB och
exponerar det som sensorer och en kalender. Resultatet ska kunna visas som snygga
dashboardkort med information om nästa hämtning per kärltyp.

---

## Arkitektur

```
Home Assistant
└── custom_components/hemab/
    ├── __init__.py          – setup_entry / unload_entry
    ├── manifest.json        – metadata, beroenden
    ├── config_flow.py       – UI-konfiguration med autokomplett
    ├── coordinator.py       – DataUpdateCoordinator (hämtning + parsning)
    ├── sensor.py            – SensorEntity per kärl
    ├── calendar.py          – CalendarEntity med alla hämtningar
    ├── const.py             – konstanter
    ├── strings.json         – UI-strängar
    └── translations/
        ├── sv.json
        └── en.json
```

Befintlig hämtningskod (`autocomplete()`, `get_schedule()`, `_parse_search_hits()`)
lyfts ur `hemab_schedule.py` till en fristående `hemab_api.py` som både CLI:t och
integrationen importerar.

---

## Entiteter

### Sensorer — en per kärltyp och gata

| Entitet | Tillstånd | Exempel |
|---------|-----------|---------|
| `sensor.hemab_<gata>_<kärl>_next` | Nästa hämtningsdatum | `2026-04-10` |

**Attribut:**
```yaml
friendly_name: "Södra Strömsborgsgatan – Fyrfackskärl 2"
veckodag: Torsdag
dagar_kvar: 2
veckor: [1, 3, 5, 7, ...]   # alla hämtningsveckor under året
nästa_veckonummer: 15
```

Sensorn uppdateras dagligen via koordinatorn. `dagar_kvar` räknas om
automatiskt varje dag utan nytt API-anrop.

### Kalender

`calendar.hemab_<gata>` — ett `CalendarEntity` med ett event per planerad
hämtning för alla kärl under hela året. Varje event är ett heldagsevent:

```
2026-04-10: Fyrfackskärl 2 – HEMAB
2026-04-10: Fyrfackskärl 1 – HEMAB
2026-04-24: Fyrfackskärl 2 – HEMAB
...
```

Kalendern möjliggör integration med Google Calendar, iCal-export m.m.

---

## Konfigurationsflöde (Config Flow)

Konfigureras helt via UI (Inställningar → Integrationer → Lägg till → HEMAB).

**Steg 1 – Sök gatunamn:**
- Textfält: "Gatunamn"
- Anropar autokomplett-API:et live (via `async_get_suggestions` i config flow)
- Visar matchande gator som valbara alternativ

**Steg 2 – Välj gata:**
- Dropdown med träffar från autokomplett
- Vid val hämtas och valideras schemat direkt

**Resultat:**
- En `ConfigEntry` per gata
- Möjligt att lägga till flera gator

---

## Datumberäkning

HEMAB returnerar veckonummer och veckodag, inte faktiska datum:

```
veckodag: "Torsdag"
veckor:   [1, 3, 5, 7, 9, ...]
```

Omvandling till datum sker i koordinatorn med Pythons `datetime`-bibliotek:

```python
import datetime

VECKODAGAR = {
    "måndag": 0, "tisdag": 1, "onsdag": 2, "torsdag": 3,
    "fredag": 4, "lördag": 5, "söndag": 6,
}

def vecka_till_datum(år: int, vecka: int, veckodag: str) -> datetime.date:
    dag_offset = VECKODAGAR[veckodag.lower()]
    # ISO: vecka 1, dag 1 = första måndagen på/efter 4 jan
    return datetime.date.fromisocalendar(år, vecka, dag_offset + 1)

def nästa_hämtning(veckor: list[int], veckodag: str) -> datetime.date:
    idag = datetime.date.today()
    år = idag.isocalendar()[0]
    for v in sorted(veckor):
        datum = vecka_till_datum(år, v, veckodag)
        if datum >= idag:
            return datum
    # Inga fler hämtningar i år — ta första veckan nästa år
    return vecka_till_datum(år + 1, sorted(veckor)[0], veckodag)
```

---

## Uppdateringsfrekvens

- **Schema** (veckor/kärl): hämtas en gång per dygn kl. 04:00
  via `DataUpdateCoordinator` med `update_interval=timedelta(hours=24)`
- **Nästa datum / dagar kvar**: beräknas lokalt vid varje HA-omstart och
  vid midnatt utan extra API-anrop (via `async_update` i sensorn)

---

## Dashboardkort

### Alternativ A — Inbyggda kort (ingen HACS krävs)

```yaml
type: entities
title: Sophämtning
entities:
  - entity: sensor.hemab_sodra_stromsborgsgatan_fyrfackskarl_2_next
    name: Fyrfackskärl 2
    secondary_info: last-changed
  - entity: sensor.hemab_sodra_stromsborgsgatan_fyrfackskarl_1_next
    name: Fyrfackskärl 1
```

### Alternativ B — Mushroom Cards (HACS)

```yaml
type: custom:mushroom-template-card
primary: Fyrfackskärl 2
secondary: >
  {{ states('sensor.hemab_sodra_stromsborgsgatan_fyrfackskarl_2_next')
     | as_datetime | relative_time }}
icon: mdi:trash-can-outline
icon_color: >
  {% if state_attr('sensor...', 'dagar_kvar') | int <= 1 %}red
  {% elif state_attr('sensor...', 'dagar_kvar') | int <= 3 %}orange
  {% else %}green{% endif %}
```

### Alternativ C — Kalendervy

Lägg till `calendar.hemab_sodra_stromsborgsgatan` i ett
`type: calendar`-kort för att se alla kommande hämtningar i månadsvy.

---

## Notiser (valfritt)

Automation som skickar notis kvällen före hämtning:

```yaml
automation:
  alias: "HEMAB – påminnelse sophämtning"
  trigger:
    platform: template
    value_template: >
      {{ state_attr('sensor.hemab_...', 'dagar_kvar') | int == 1 }}
  action:
    service: notify.mobile_app
    data:
      title: "Sophämtning imorgon"
      message: >
        {{ state_attr('sensor.hemab_...', 'friendly_name') }} hämtas imorgon.
```

---

## Implementationsordning

1. **Refaktorera** `hemab_schedule.py` → extrahera API-logik till `hemab_api.py`
2. **Skapa** `custom_components/hemab/` med `manifest.json` och `const.py`
3. **Implementera** `coordinator.py` med `DataUpdateCoordinator`
4. **Implementera** `config_flow.py` med autokomplett-stöd
5. **Implementera** `sensor.py`
6. **Implementera** `calendar.py`
7. **Testa** manuellt i en HA-instans (kan köras i Docker lokalt)
8. **Lägg till** `strings.json` + `translations/sv.json`

---

## Tekniska beroenden

```json
{
  "requirements": ["requests>=2.28", "beautifulsoup4>=4.12"],
  "iot_class": "cloud_polling",
  "version": "1.0.0"
}
```

`requests` och `bs4` är inte inbyggda i HA — de deklareras i `manifest.json`
och installeras automatiskt av HA vid setup.

Alternativt kan `aiohttp` (inbyggt i HA) användas för asynkrona anrop —
det är att föredra i en färdig integration för att inte blockera event loop:en.
