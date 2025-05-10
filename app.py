import os
from flask import (
    Flask, request, session, redirect, url_for,
    render_template, Response, stream_with_context
)
from flask_session import Session
from werkzeug.utils import secure_filename
import google_auth_oauthlib.flow

from facebook_bdays.calendar_service import get_calendar_service
from facebook_bdays.ics_parser       import fetch_fb_birthdays_from_ics
from facebook_bdays.birthdays        import insert_birthdays_generator

# allow HTTP for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)
app.config.update(
    SESSION_TYPE='filesystem',
    SESSION_FILE_DIR='./.flask_session/',
    SESSION_PERMANENT=False,
    UPLOAD_FOLDER='./.uploads'
)
Session(app)

SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRETS_FILE = 'credentials.json'
CALENDAR_NAME = "facebook Birthdays"


@app.route('/', methods=['GET','POST'])
def index():
    error    = None
    if request.method == 'POST':
        action = request.form['action']

        # Only clear the old upload info—do NOT clear session['credentials']
        session.pop('ics_path', None)
        session.pop('reminder', None)
        session['action'] = action
        # only block “Add” if we **can** check for the calendar
        if action == 'add' and 'credentials' in session:
            svc   = get_calendar_service()
            items = svc.calendarList().list().execute().get('items', [])
            if any(c['summary'] == CALENDAR_NAME for c in items):
                error = f'You already have a calendar named "{CALENDAR_NAME}". Delete it first.'
                return render_template('index.html', error=error)
            
        elif action == 'delete' and 'credentials' in session:
            svc   = get_calendar_service()
            items = svc.calendarList().list().execute().get('items', [])
            exists = any(c['summary'] == CALENDAR_NAME for c in items)
            if not exists:
                error = f'No "{CALENDAR_NAME}" calendar to delete.'
                return render_template('index.html', error=error)
        
        if action == 'add':
            f = request.files.get('ics_file')
            if not f or not f.filename:
                error = "Please upload a .ics file to proceed."
            elif not f.filename.lower().endswith('.ics'):
                error = "Only files ending in .ics are allowed."
            if error:
                return render_template('index.html', error=error)

            fn = secure_filename(f.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            f.save(path)
            session['ics_path'] = path
            session['reminder']  = int(request.form['reminder'])
        return redirect(url_for('oauth2callback'))

    return render_template('index.html', error=error)

@app.route('/oauth2callback')
def oauth2callback():
    # Rebuild the Flow for this callback
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    if 'code' not in request.args:
        auth_url, state = flow.authorization_url(prompt='consent')
        session['state'] = state
        return redirect(auth_url)

    # Second pass: user came back from Google
    flow.fetch_token(
        authorization_response=request.url,
        state=session.pop('state')
    )
    creds = flow.credentials
    # Save only the small credentials dict in session
    session['credentials'] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    return redirect(url_for('process'))


@app.route('/process')
def process():
    service = get_calendar_service()
    action  = session['action']

    if action == 'add':
        
        friends  = fetch_fb_birthdays_from_ics(session['ics_path'])
        reminder = session['reminder']
        total    = len(friends)

        def gen_add():
            # render initial template
            yield render_template('process.html', action="Adding")
            count = 0
            for name, status in insert_birthdays_generator(
                    service, friends, reminder, CALENDAR_NAME):
                count += 1
                pct = int(count / total * 100)
                yield f"<script>update({pct});</script>\n"
            session['calendar_created'] = True
            yield f"<script>finished('{count}/{total} added')</script>"
            
        return Response(stream_with_context(gen_add()),
                        content_type='text/html; charset=utf-8')

    else:  # delete
        def gen_del():
            yield render_template('process.html', action="Deleting")
            # find the calendar
            items = service.calendarList().list().execute().get('items', [])
            session.pop('calendar_created', None)
            cal = next((c for c in items if c['summary']==CALENDAR_NAME), None)
            service.calendars().delete(calendarId=cal['id']).execute()
            yield "<script>update(100);</script>\n"
            yield "<script>finished('Calendar deleted')</script>"

        return Response(stream_with_context(gen_del()),
                        content_type='text/html; charset=utf-8')


if __name__ == '__main__':
    app.run(debug=True)
