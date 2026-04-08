#!/usr/bin/env python3
"""
HEMAB ICS-server

Serverar tömningsschema från HEMAB som en prenumerationsbar ICS-kalender.

Endpoints:
  GET /ics?gata=<gatunamn>[&dag_fore=true][&paminnelse=<minuter>]
  GET /health

Exempel:
  /ics?gata=Södra+Strömsborgsgatan
  /ics?gata=Södra+Strömsborgsgatan&dag_fore=true&paminnelse=720
"""

import os
import requests
from flask import Flask, request, Response
from hemab_api import get_schedule
from ics_builder import build_calendar

app = Flask(__name__)


@app.route("/ics")
def ics():
    gata = request.args.get("gata", "").strip()
    if not gata:
        return Response(
            "Parametern 'gata' saknas.\n"
            "Exempel: /ics?gata=Södra+Strömsborgsgatan\n"
            "Med påminnelse: /ics?gata=Södra+Strömsborgsgatan&dag_fore=true&paminnelse=720",
            status=400,
            mimetype="text/plain; charset=utf-8",
        )

    dag_fore = request.args.get("dag_fore", "false").lower() == "true"

    try:
        paminnelse_min = int(request.args.get("paminnelse", "0"))
    except ValueError:
        paminnelse_min = 0

    try:
        schedules = get_schedule(gata)
    except requests.HTTPError as e:
        return Response(f"HTTP-fel mot HEMAB: {e}", status=502, mimetype="text/plain; charset=utf-8")
    except requests.RequestException as e:
        return Response(f"Nätverksfel: {e}", status=502, mimetype="text/plain; charset=utf-8")

    if not schedules:
        return Response(
            f"Inga hämtningsscheman hittades för '{gata}'.",
            status=404,
            mimetype="text/plain; charset=utf-8",
        )

    ical_bytes = build_calendar(schedules, dag_fore=dag_fore, paminnelse_min=paminnelse_min)

    filename = gata.replace(" ", "_") + ".ics"
    return Response(
        ical_bytes,
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
