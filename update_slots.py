# Reads free mivdak slots of every registrar from Calendly (public booking data)
# and writes slots.json for the page. Runs in GitHub Actions every ~10 minutes.
import json, urllib.request, datetime, sys

REGISTRARS = [
    {"id": "aviram",  "name": "אבירם היכל",  "role": "מייסד העוצמה בחינוך",
     "img": "img/aviram.jpg",  "url": "https://calendly.com/aviram-heichal-power-in-education/30min",
     "uuid": "5a40a097-c837-4cd0-bc8e-2a11ecd7edb3"},
    {"id": "emanuel", "name": "עמנואל חצור", "role": "מומחה למבדקי למידה",
     "img": "img/emanuel.jpg", "url": "https://calendly.com/bearibear6/meet-with-me",
     "uuid": "4a687959-9732-4f85-8e01-219ebc6b8b85"},
    {"id": "orly",    "name": "אורלי חיון",  "role": "מומחית למבדקי למידה",
     "img": "img/orly.jpg",    "url": "https://calendly.com/orliot/30min",
     "uuid": "cac8ca26-6d92-43e6-8abd-333d28731803"},
]
DAYS_AHEAD = 70
# מועדים שחסומים ידנית (פגישה שלא מופיעה ביומן שקלנדלי בודק). "רשם": ["YYYY-MM-DD" או "YYYY-MM-DDTHH:MM"]
BLOCKED = {"aviram": ["2026-11-29"]}  # 26.11: לאבירם יש פגישה בבוקר 29.11
MIN_HOURS_AHEAD = 12          # safety net
MIN_DAYS_AHEAD = 2            # Aviram 26.11: earliest meeting = 2 calendar days from today (time for questionnaires, no same/next-day surprises for coaches)

IL = datetime.timezone(datetime.timedelta(hours=2))
now = datetime.datetime.now(datetime.timezone.utc)
start = now.astimezone(IL).date()
end = start + datetime.timedelta(days=DAYS_AHEAD)

def fetch(uuid, a, b):
    url = ("https://calendly.com/api/booking/event_types/%s/calendar/range"
           "?timezone=Asia%%2FJerusalem&diagnostics=false&range_start=%s&range_end=%s" % (uuid, a, b))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

slots, errors = [], []
for reg in REGISTRARS:
    try:
        # Calendly answers up to ~30 days per call -> ask in chunks
        a = start
        while a < end:
            b = min(a + datetime.timedelta(days=27), end)
            data = fetch(reg["uuid"], a.isoformat(), b.isoformat())
            for d in data.get("days", []):
                if d.get("status") != "available":
                    continue
                for s in d.get("spots", []):
                    if s.get("status", "available") != "available":
                        continue
                    t = datetime.datetime.fromisoformat(s["start_time"])
                    if (t - now).total_seconds() < MIN_HOURS_AHEAD * 3600:
                        continue
                    if t.astimezone(IL).date() < start + datetime.timedelta(days=MIN_DAYS_AHEAD):
                        continue
                    if any(s["start_time"].startswith(b) for b in BLOCKED.get(reg["id"], [])):
                        continue
                    slots.append({"r": reg["id"], "t": s["start_time"]})
            a = b + datetime.timedelta(days=1)
    except Exception as e:
        errors.append("%s: %s" % (reg["id"], e))

# de-duplicate + sort
seen, uniq = set(), []
for s in sorted(slots, key=lambda x: (x["t"], x["r"])):
    k = (s["r"], s["t"])
    if k not in seen:
        seen.add(k); uniq.append(s)

out = {
    "updated": now.isoformat(timespec="seconds"),
    "registrars": [{k: r[k] for k in ("id", "name", "role", "img", "url")} for r in REGISTRARS],
    "slots": uniq,
    "errors": errors,
}
old = None
try:
    old = json.load(open("slots.json", encoding="utf-8"))
except Exception:
    pass
# keep the last good list of a registrar whose fetch failed (never show an empty page because of a hiccup)
if errors and old:
    failed = {e.split(":")[0] for e in errors}
    keep = [s for s in old.get("slots", []) if s["r"] in failed and
            datetime.datetime.fromisoformat(s["t"]).astimezone(IL).date() >= start + datetime.timedelta(days=MIN_DAYS_AHEAD)]
    out["slots"] = sorted(out["slots"] + keep, key=lambda x: (x["t"], x["r"]))

if old and old.get("slots") == out["slots"] and old.get("errors") == out["errors"] \
        and old.get("registrars") == out["registrars"]:
    # nothing changed -> only refresh the time stamp once an hour (fewer commits)
    try:
        prev = datetime.datetime.fromisoformat(old["updated"])
        if (now - prev).total_seconds() < 3600:
            print("no change"); sys.exit(0)
    except Exception:
        pass
json.dump(out, open("slots.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written", len(out["slots"]), "slots", errors)
