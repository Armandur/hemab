"""
Bygger en ICS-kalender från HEMAB-schemadata.

Exporterade funktioner:
  build_calendar(schedules, dag_fore, paminnelse_tid, paminnelse_dag) -> bytes
  collect_events(schedules, dag_fore) -> list[dict]
"""

import datetime
from icalendar import Calendar, Event, Alarm
from hemab_api import KÄRL_INNEHÅLL, alla_datum


def build_calendar(
    schedules: list[dict],
    dag_fore: bool = False,
    paminnelse_tid: str | None = None,
    paminnelse_dag: str = "fore",
) -> bytes:
    """
    Skapar en ICS-fil från ett schema returnerat av hemab_api.get_schedule().

    Kärl som hämtas samma dag slås ihop till en enda händelse.

    Args:
        schedules:      Lista av scheman (ett per gatunamn).
        dag_fore:       Om True sätts händelsen till dagen *innan* hämtning.
        paminnelse_tid: Klockslag för påminnelse i formatet "HH:MM", eller None.
        paminnelse_dag: "fore" = dagen innan händelsen, "samma" = samma dag.

    Returns:
        ICS-fil som bytes.
    """
    cal = Calendar()
    cal.add("prodid", "-//HEMAB Tömningsschema//hemab.se//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "HEMAB Sophämtning")
    cal.add("x-wr-timezone", "Europe/Stockholm")

    for ev in collect_events(schedules, dag_fore):
        event_date = datetime.date.fromisoformat(ev["date"])
        pickup_date = datetime.date.fromisoformat(ev["pickup_date"])

        entry = Event()
        entry.add("summary", _summary(ev["karl_list"], dag_fore))
        entry.add("dtstart", event_date)
        entry.add("dtend", event_date + datetime.timedelta(days=1))
        entry.add("description", _description(ev["gatunamn"], ev["karl_list"], pickup_date, dag_fore))
        entry.add("uid", f"{pickup_date.isoformat()}-{ev['gatunamn'].replace(' ', '-')}@hemab")

        if paminnelse_tid:
            entry.add_component(_alarm(ev["karl_list"], paminnelse_tid, paminnelse_dag, dag_fore))

        cal.add_component(entry)

    return cal.to_ical()


def collect_events(schedules: list[dict], dag_fore: bool) -> list[dict]:
    """
    Bearbetar scheman till en sorterad lista av händelser.
    Kärl med samma datum och gatunamn slås ihop till en händelse.
    """
    idag = datetime.date.today()
    grouped: dict[tuple, dict] = {}

    for s in schedules:
        gatunamn = s.get("gatunamn") or "Okänd gata"
        veckodag = s.get("veckodag") or ""

        for entry in s.get("schema", []):
            karl = entry.get("kärl") or ""
            veckor_str = entry.get("veckor") or ""
            innehall = KÄRL_INNEHÅLL.get(karl, [])

            for pickup_date in alla_datum(veckor_str, veckodag):
                if pickup_date < idag:
                    continue
                event_date = pickup_date - datetime.timedelta(days=1) if dag_fore else pickup_date
                key = (event_date, gatunamn)
                if key not in grouped:
                    grouped[key] = {
                        "date": event_date.isoformat(),
                        "pickup_date": pickup_date.isoformat(),
                        "gatunamn": gatunamn,
                        "karl_list": [],
                    }
                grouped[key]["karl_list"].append({"karl": karl, "innehall": innehall})

    return [v for _, v in sorted(grouped.items())]


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

def _summary(karl_list: list[dict], dag_fore: bool) -> str:
    if len(karl_list) == 1:
        return f"Ställ ut {karl_list[0]['karl']}" if dag_fore else f"Sophämtning – {karl_list[0]['karl']}"
    return "Ställ ut tunnorna" if dag_fore else "Sophämtning"


def _description(
    gatunamn: str,
    karl_list: list[dict],
    pickup_date: datetime.date,
    dag_fore: bool,
) -> str:
    parts = []
    if dag_fore:
        parts.append(f"Hämtning sker {pickup_date.isoformat()}")
    for kv in karl_list:
        line = kv["karl"]
        if kv["innehall"]:
            line += f": {', '.join(kv['innehall'])}"
        parts.append(line)
    parts.append(f"Gata: {gatunamn}")
    return "\n".join(parts)


def _alarm(karl_list: list[dict], tid: str, dag: str, event_is_dag_fore: bool) -> Alarm:
    h, m = map(int, tid.split(":"))
    # Trigger relativt händelsens midnatt
    if dag == "fore":
        trigger = datetime.timedelta(hours=h - 24, minutes=m)   # negativt = före midnatt
    else:
        trigger = datetime.timedelta(hours=h, minutes=m)         # positivt = efter midnatt

    multi = len(karl_list) > 1
    if event_is_dag_fore:
        desc = ("Dags att ställa ut tunnorna imorgon!" if multi
                else f"Dags att ställa ut {karl_list[0]['karl']} imorgon!")
    else:
        desc = ("Sophämtning imorgon – ställ ut tunnorna!" if multi
                else f"Sophämtning: {karl_list[0]['karl']}")

    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", desc)
    alarm.add("trigger", trigger)
    return alarm
