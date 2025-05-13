# Use the official slim Python base image
FROM python:3.10-slim

# Set a working directory
WORKDIR /app

# Copy & install dependencies first (leverages layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Allow OAuth over HTTP in dev (Cloud Run will be HTTPS)
ENV OAUTHLIB_INSECURE_TRANSPORT=1

# Tell Cloud Run which port to listen on
ENV PORT=8080

# Default command: use Gunicorn to serve your Flask app
CMD exec gunicorn --bind 0.0.0.0:$PORT app:app
