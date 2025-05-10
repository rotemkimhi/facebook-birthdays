from googleapiclient.errors import HttpError

def get_or_create_calendar_id(service, summary="facebook Birthdays"):
    """Finds—or creates—a calendar named `summary` and returns its ID."""
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

def insert_birthdays_generator(service,
                                birthdays,
                                reminder_hours,
                                calendar_name="Birthdays"):
    """
    Yields (name, status) as it inserts each birthday event.
    """
    from datetime import date
    import hashlib

    cal_id = get_or_create_calendar_id(service, calendar_name)
    today  = date.today()
    for b in birthdays:
        # 1) compute next year occurrence
        yr = today.year if (today.month, today.day) <= (b["month"], b["day"]) \
                             else today.year + 1
        start_str = date(yr, b["month"], b["day"]).isoformat()

        # 2) stable MD5-based ID
        raw      = f"{b['name']}-{b['month']:02d}{b['day']:02d}".encode()
        event_id = hashlib.md5(raw).hexdigest()

        # 3) build the event payload
        event = {
            "id": event_id,
            "summary": f"{b['name']}'s Birthday 🎂",
            "start": {"date": start_str},
            "end":   {"date": start_str},
            "recurrence": ["RRULE:FREQ=YEARLY"],
            "reminders": {
                "useDefault": False,
                "overrides": [{
                    "method": "popup",
                    "minutes": reminder_hours * 60
                }]
            }
        }

        # 4) try to insert & yield status
        try:
            service.events().insert(calendarId=cal_id, body=event).execute()
            yield b["name"], "added"
        except Exception as e:
            msg = getattr(e, "error_details", str(e))
            yield b["name"], f"error: {msg}"

def delete_calendar_generator(service, calendar_name):
    """
    Yields two steps: before and after deleting the entire calendar.
    """
    # 1) find the calendar ID
    page_token = None
    cal_id = None
    while True:
        resp = service.calendarList().list(pageToken=page_token).execute()
        for cal in resp.get("items", []):
            if cal.get("summary") == calendar_name:
                cal_id = cal["id"]
                break
        if cal_id or not resp.get("nextPageToken"):
            break
        page_token = resp.get("nextPageToken")

    if not cal_id:
        raise ValueError(f'No calendar named "{calendar_name}" found.')

    # 2) signal start
    yield calendar_name, "deleting calendar"

    # 3) delete whole calendar
    try:
        service.calendars().delete(calendarId=cal_id).execute()
        yield calendar_name, "deleted"
    except HttpError as e:
        yield calendar_name, f"error: {e.error_details}"