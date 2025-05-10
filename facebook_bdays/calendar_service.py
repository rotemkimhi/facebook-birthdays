# facebook_bdays/calendar_service.py

import google.oauth2.credentials
import googleapiclient.discovery
from flask import session

SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRETS_FILE = 'credentials.json'

def get_calendar_service():
    """
    Reads OAuth tokens from session and builds the Calendar service.
    Assumes session['credentials'] is already populated.
    """
    creds_data = session.get('credentials')
    if not creds_data:
        raise RuntimeError("No credentials in session; run OAuth flow first.")
    creds = google.oauth2.credentials.Credentials(**creds_data)
    return googleapiclient.discovery.build('calendar', 'v3', credentials=creds)
