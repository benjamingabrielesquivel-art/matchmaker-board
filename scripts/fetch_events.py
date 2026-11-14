#!/usr/bin/env python3
"""Fetch IDFA's industry events per day, with ticket status, into events.json.

Reads the public festival schedule that festival.idfa.nl itself uses.
Keeps only facts: title, time, place, who it is for, ticket status and a link.
Usage: python3 -I scripts/fetch_events.py events.json
"""
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://my.idfa.nl/api/graphql/festival"
SITE = "https://festival.idfa.nl/en"
FIRST_DAY = date(2026, 11, 12)
LAST_DAY = date(2026, 11, 22)
SHOW_TYPES = ["Industry", "Industry & Public"]

QUERY = """query searchScheduleHits($filters: [ScheduleFilterInput!]!) {
  searchSchedule(filters: $filters) {
    totalHits
    hits {
      __typename id fullTitle ticketAvailabilityStatus externalSaleLink noSale
      publicationContext startOn endOn location
      audience { key translation }
      film { id fullPreferredTitle }
      composition { id fullTitle }
    }
  }
}"""


def slug(title):
    return re.sub(r"\s+", "-", (title or "").strip().lower())


def ask(day):
    body = json.dumps({
        "operationName": "searchScheduleHits",
        "variables": {"filters": [
            {"key": "DAY", "value": [day.isoformat()]},
            {"key": "SHOW_TYPE", "value": SHOW_TYPES},
        ]},
        "query": QUERY,
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "matchmaker-board/1.0 (events per day)",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"])[:300])
    return data["data"]["searchSchedule"]["hits"]


def tidy(hit):
    comp, film = hit.get("composition"), hit.get("film")
    if comp and comp.get("id"):
        link = f"{SITE}/composition/{comp['id']}/{slug(comp.get('fullTitle'))}/"
    elif film and film.get("id"):
        link = f"{SITE}/film/{film['id']}/{slug(film.get('fullPreferredTitle'))}/"
    else:
        link = f"{SITE}/collectie/"
    status = hit.get("ticketAvailabilityStatus")
    if hit.get("noSale"):
        status = "NO_SALE"
    elif hit.get("externalSaleLink"):
        status = status or "EXTERNAL"
    return {
        "id": hit.get("id"),
        "title": (hit.get("fullTitle") or "").strip(),
        "start": hit.get("startOn"),
        "end": hit.get("endOn"),
        "location": (hit.get("location") or "").strip(),
        "audience": ((hit.get("audience") or {}).get("translation") or "").strip(),
        "status": status or "UNKNOWN",
        "link": link,
    }


def main(out_path):
    days = []
    d = FIRST_DAY
    while d <= LAST_DAY:
        hits = ask(d)
        events = sorted((tidy(h) for h in hits), key=lambda e: (e["start"] or "", e["title"]))
        if events:
            days.append({"date": d.isoformat(), "events": events})
        d += timedelta(days=1)
        time.sleep(0.5)
    if not days:
        raise SystemExit("No industry events found; events.json left as it was.")
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"{SITE}/collectie/",
        "days": days,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    total = sum(len(x["events"]) for x in days)
    sold = sum(1 for x in days for e in x["events"] if e["status"] == "SOLD_OUT")
    print(f"{total} industry events over {len(days)} days, {sold} sold out -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "events.json")
