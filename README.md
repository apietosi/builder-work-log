# Builder Work Log — hosted version

Mobile web app for a sign-installation crew to log completed jobs from the
field: date, crew, builder, location, work performed, photos, and billing
status. Includes search, per-builder filters, a "needs billed" list, stats,
and CSV export.

## Deploy (Render)

- **Runtime:** Python
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app:app`
- **Environment variables:**
  - `DATABASE_URL` — Postgres connection string (jobs *and* photos are stored
    in the database, so the web service itself can be free/ephemeral)
  - `WORKLOG_PIN` — shared crew PIN that gates every page
  - `WORKLOG_SECRET` — any long random string (signs the login cookie)

Photos are auto-compressed (max 1600 px, JPEG) before storage.

After the first deploy, visit `/import` once and upload `work_log_backup.csv`
to load the job history. The import route locks itself once the database has
data.

## Run locally

Without `DATABASE_URL` it falls back to a local SQLite file:

    pip install flask pillow
    python app.py     # http://localhost:5078
