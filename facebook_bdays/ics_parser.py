from icalendar import Calendar

def fetch_fb_birthdays_from_ics(path):
    # Parse a local .ics file and return a list of birthdays.
    with open(path, "rb") as f:
        raw = f.read()
    cal = Calendar.from_ical(raw)
    out = []
    for comp in cal.walk():
        if comp.name == "VEVENT":
            uid  = comp.get("uid")
            name = comp.get("summary").replace("’s Birthday","").strip()
            dt   = comp.decoded("dtstart")
            out.append({
                "uid":   uid,
                "name":  name,
                "month": dt.month,
                "day":   dt.day
            })
    return out