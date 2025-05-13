# calendar_service.py

import google.oauth2.credentials
import googleapiclient.discovery
from flask import session

SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRETS_FILE = 'credentials.json'

def get_calendar_service():
    # Reads OAuth tokens from session and builds the Calendar service. 
    creds_data = session.get('credentials')
    if not creds_data:
        raise RuntimeError("No credentials in session; run OAuth flow first.")
    creds = google.oauth2.credentials.Credentials(**creds_data)
    return googleapiclient.discovery.build('calendar', 'v3', credentials=creds)

def delete_calendar_if_exists(service, summary):
    # look for an existing calendar
    items = service.calendarList().list().execute().get("items", [])
    existing = next((c for c in items if c["summary"] == summary), None)
    if existing:
        # delete from calendarList and then delete the calendar itself
        service.calendarList().delete(calendarId=existing["id"]).execute()
        service.calendars().delete   (calendarId=existing["id"]).execute()
        return True
    return False
