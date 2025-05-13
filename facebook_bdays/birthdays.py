import hashlib
import time
from datetime import date
from itertools import islice
from googleapiclient.errors import HttpError
import googleapiclient.discovery
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_or_create_calendar_id(service, summary="facebook Birthdays"):
    # Finds or creates a calendar named `summary` and returns its ID.
    page_token = None
    while True:
        resp = service.calendarList().list(pageToken=page_token).execute()
        for cal in resp.get("items", []):
            if cal.get("summary") == summary:
                return cal["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    created = service.calendars().insert(body={
        "summary": summary,
        "timeZone": "UTC"
    }).execute()
    service.calendarList().insert(body={"id": created["id"]}).execute()
    return created["id"]

def insert_birthdays_generator(service, birthdays, reminder_hours, calendar_name):
    # insert birthdays into a Google Calendar, batching at 50
    cal_id = get_or_create_calendar_id(service, calendar_name)
    today  = date.today()
    total  = len(birthdays)
    if total == 0:
        return
    # Helper: break the list into 50-item chunks
    def chunked(it, n=50):
        it = iter(it)
        while True:
            batch = list(islice(it, n))
            if not batch:
                return
            yield batch
    done = 0
    for batch in chunked(birthdays, 50):
        batch_req = service.new_batch_http_request()
        statuses = {}
        mapping  = {}
        # Callback always has a matching mapping entry
        def callback(request_id, response, exception):
            b = mapping[request_id]
            statuses[b["name"]] = "added" if exception is None else f"error: {exception}"
        # Queue up each event insert
        for b in batch:
            uid = b.get("uid", "")
            if uid:
                event_id = hashlib.md5(uid.encode("utf-8")).hexdigest()
            else:
                # fallback to name+date if no uid
                raw = f"{b['name']}-{b['month']:02d}{b['day']:02d}".encode()
                event_id = hashlib.md5(raw).hexdigest()
            mapping[event_id] = b

            yr = today.year if (today.month, today.day) <= (b["month"], b["day"]) else today.year + 1
            start_iso = date(yr, b["month"], b["day"]).isoformat()
            event = {
                "id": event_id,
                "summary": f"{b['name']}'s Birthday",
                "start": {"date": start_iso},
                "end":   {"date": start_iso},
                "recurrence": ["RRULE:FREQ=YEARLY"],
                "reminders": {
                    "useDefault": False,
                    "overrides": [{
                        "method":  "popup",
                        "minutes": reminder_hours * 60
                    }]
                }
            }
            batch_req.add(
                service.events().insert(calendarId=cal_id, body=event),
                request_id=event_id,
                callback=callback
            )

        # Exponential backoff on rate-limit
        backoff = 1
        while True:
            try:
                batch_req.execute()
                break
            except HttpError as e:
                # look for a Rate Limit Exceeded 403
                if getattr(e, "resp", None) and e.resp.status == 403 \
                   and "rateLimitExceeded" in str(e):
                    print(f"Rate limit hit, backing off {backoff}s…")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 16)
                    continue
                print("Batch insert failed:", e)
                for b in batch:
                    statuses[b["name"]] = f"error: {e}"
                break
        # Yield each birthday with the same pct
        done += len(batch)
        pct   = int(done / total * 100)
        for b in batch:
            yield b["name"], statuses.get(b["name"], "error"), pct