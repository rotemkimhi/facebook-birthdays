import os
import threading
import uuid
from flask import (
    Flask, request, session, redirect, url_for,
    render_template, Response, jsonify, stream_with_context
)
from flask_session import Session
from werkzeug.utils import secure_filename
import google_auth_oauthlib.flow
from werkzeug.middleware.proxy_fix import ProxyFix

from facebook_bdays.calendar_service import delete_calendar_if_exists, get_calendar_service
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
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
Session(app)
PROGRESS = {}

SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRETS_FILE = 'credentials.json'
CALENDAR_NAME = "facebook Birthdays"

def do_import(job_id, service, birthdays, reminder, calendar_name):
    total = len(birthdays)
    done  = 0

    # Delete old calendar if present
    PROGRESS[job_id] = {"pct": 0, "message": "Checking for existing calendar…"}
    deleted = delete_calendar_if_exists(service, calendar_name)
    if deleted:
        PROGRESS[job_id] = {"pct": 0, "message": "Deleted old calendar, creating new one…"}
    else:
        PROGRESS[job_id] = {"pct": 0, "message": "No existing calendar, creating new one…"}

    #  Now proceed with your insert generator (which will create a fresh calendar)
    for name, status, pct in insert_birthdays_generator(
            service, birthdays, reminder, calendar_name):
        PROGRESS[job_id] = {
            "pct": pct,
            "message": f"Added ({pct * total // 100}/{total})"
        }
        done += 1

    PROGRESS[job_id] = {
        "pct": 100,
        "message": f"Done! {done}/{total} birthdays added."
    }

@app.before_request
def enforce_https_in_redirect():
    if request.headers.get("X-Forwarded-Proto", "http") == "https":
        request.environ['wsgi.url_scheme'] = 'https'

@app.route('/', methods=['GET','POST'])
def index():
    error = None
    if request.method == 'POST':
        f = request.files.get('ics_file')
        if not f or not f.filename.lower().endswith('.ics'):
            error = "Please upload a valid .ics file."
            return render_template('index.html', error=error)

        fn = secure_filename(f.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        f.save(path)

        session['ics_path']  = path
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
    service    = get_calendar_service()
    birthdays  = fetch_fb_birthdays_from_ics(session['ics_path'])
    reminder   = session['reminder']
    calendar_nm = CALENDAR_NAME

    # create a job and start it
    job_id = str(uuid.uuid4())
    session['job_id'] = job_id

    thread = threading.Thread(
        target=do_import,
        args=(job_id, service, birthdays, reminder, calendar_nm),
        daemon=True
    )
    thread.start()

    return render_template('progress.html', job_id=job_id)

@app.route('/progress')
def progress():
    job_id = request.args.get('job_id')
    data   = PROGRESS.get(job_id, {"pct": 0, "message": "No job"})
    return jsonify(data)

@app.route('/legal/')
def homepage():
    return render_template('legal/index.html')

@app.route('/legal/privacy.html')
def privacy():
    return render_template('legal/privacy.html')

@app.route('/legal/terms.html')
def terms():
    return render_template('legal/terms.html')



if __name__ == '__main__':
    app.run(debug=True)
