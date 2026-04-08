"""
Bygger en ICS-kalender från HEMAB-schemaData.

Exporterade funktioner:
  build_calendar(schedules, dag_fore, paminnelse_min) -> bytes
"""

import datetime
from icalendar import Calendar, Event, Alarm
from hemab_api import KÄRL_INNEHÅLL, alla_datum


def build_calendar(
    schedules: list[dict],
    dag_fore: bool = False,
    paminnelse_min: int = 0,
) -> bytes:
    """
    Skapar en ICS-fil från ett schema returnerat av hemab_api.get_schedule().

    Args:
        schedules:      Lista av scheman (ett per gatunamn).
        dag_fore:       Om True sätts händelsen till dagen *innan* hämtning,
                        lämpligt för påminnelse om att ställa ut tunnan.
        paminnelse_min: Minuter före händelsens start för VALARM (0 = ingen).

    Returns:
        ICS-fil som bytes, redo att serveras med Content-Type: text/calendar.
    """
    cal = Calendar()
    cal.add("prodid", "-//HEMAB Tömningsschema//hemab.se//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "HEMAB Sophämtning")
    cal.add("x-wr-timezone", "Europe/Stockholm")

    for s in schedules:
        gatunamn = s.get("gatunamn") or "Okänd gata"
        veckodag = s.get("veckodag") or ""

        for entry in s.get("schema", []):
            karl = entry.get("kärl") or ""
            veckor_str = entry.get("veckor") or ""
            innehall = KÄRL_INNEHÅLL.get(karl, [])

            idag = datetime.date.today()
            for pickup_date in alla_datum(veckor_str, veckodag):
                if pickup_date < idag:
                    continue
                event_date = pickup_date - datetime.timedelta(days=1) if dag_fore else pickup_date

                event = Event()
                event.add("summary", _summary(karl, dag_fore))
                event.add("dtstart", event_date)
                event.add("dtend", event_date + datetime.timedelta(days=1))
                event.add("description", _description(gatunamn, karl, innehall, pickup_date, dag_fore))
                event.add("uid", _uid(pickup_date, karl, gatunamn))

                if paminnelse_min > 0:
                    event.add_component(_alarm(karl, paminnelse_min, dag_fore))

                cal.add_component(event)

    return cal.to_ical()


def _summary(karl: str, dag_fore: bool) -> str:
    if dag_fore:
        return f"Ställ ut {karl}"
    return f"Sophämtning – {karl}"


def _description(
    gatunamn: str,
    karl: str,
    innehall: list[str],
    pickup_date: datetime.date,
    dag_fore: bool,
) -> str:
    parts = []
    if dag_fore:
        parts.append(f"Hämtning sker {pickup_date.isoformat()}")
    if innehall:
        parts.append(f"Fraktioner: {', '.join(innehall)}")
    parts.append(f"Gata: {gatunamn}")
    return "\n".join(parts)


def _uid(pickup_date: datetime.date, karl: str, gatunamn: str) -> str:
    safe_karl = karl.replace(" ", "-")
    safe_gata = gatunamn.replace(" ", "-")
    return f"{pickup_date.isoformat()}-{safe_karl}-{safe_gata}@hemab"


def _alarm(karl: str, paminnelse_min: int, dag_fore: bool) -> Alarm:
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    if dag_fore:
        alarm.add("description", f"Dags att ställa ut {karl} imorgon!")
    else:
        alarm.add("description", f"Sophämtning idag: {karl}")
    alarm.add("trigger", datetime.timedelta(minutes=-paminnelse_min))
    return alarm
