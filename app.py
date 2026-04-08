#!/usr/bin/env python3
"""
HEMAB ICS-server

Serverar tömningsschema från HEMAB som en prenumerationsbar ICS-kalender.

Endpoints:
  GET /                                              – Webbgränssnitt
  GET /autocomplete?term=<sökterm>                   – Gatunamnsförslag (JSON)
  GET /preview?gata=<gatunamn>[&dag_fore=true]       – Schemaförhandsvisning (JSON)
  GET /ics?gata=<gatunamn>[&dag_fore=true][&paminnelse=<min>]  – ICS-fil
  GET /health
"""

import os
import datetime
import requests
from flask import Flask, request, Response, render_template, jsonify
from hemab_api import get_schedule, autocomplete as hemab_autocomplete, alla_datum, KÄRL_INNEHÅLL
from ics_builder import build_calendar

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/autocomplete")
def autocomplete():
    term = request.args.get("term", "").strip()
    if not term:
        return jsonify([])
    try:
        return jsonify(hemab_autocomplete(term))
    except Exception:
        return jsonify([])


@app.route("/preview")
def preview():
    gata = request.args.get("gata", "").strip()
    if not gata:
        return jsonify({"error": "Parametern 'gata' saknas"}), 400

    dag_fore = request.args.get("dag_fore", "false").lower() == "true"

    try:
        schedules = get_schedule(gata)
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    if not schedules:
        return jsonify({"error": f"Inga scheman hittades för '{gata}'"}), 404

    idag = datetime.date.today()
    events = []

    for s in schedules:
        gatunamn = s.get("gatunamn") or gata
        veckodag = s.get("veckodag") or ""

        for entry in s.get("schema", []):
            karl = entry.get("kärl") or ""
            veckor_str = entry.get("veckor") or ""
            innehall = KÄRL_INNEHÅLL.get(karl, [])

            for pickup_date in alla_datum(veckor_str, veckodag):
                if pickup_date < idag:
                    continue
                event_date = pickup_date - datetime.timedelta(days=1) if dag_fore else pickup_date
                events.append({
                    "date": event_date.isoformat(),
                    "pickup_date": pickup_date.isoformat(),
                    "karl": karl,
                    "innehall": innehall,
                    "gatunamn": gatunamn,
                })

    events.sort(key=lambda e: e["date"])
    return jsonify({"events": events, "gata": gata})


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
