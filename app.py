"""Builder Work Log — hosted version (Render + Postgres).

Set DATABASE_URL (Postgres) and WORKLOG_PIN in the environment.
Without DATABASE_URL it falls back to a local SQLite file (for testing).
Photos are compressed and stored in the database, so nothing is lost
when the web service restarts.
"""
import csv
import io
import os
import re
import sqlite3
import datetime
from flask import (Flask, request, redirect, url_for, render_template_string,
                   session, Response, abort)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
PIN = os.environ.get('WORKLOG_PIN', '')

BUILDERS = ['Ryan Homes', 'Dr Horton', 'Infinity', 'Heartland', 'Charter',
            'Foxlane', 'ToA', 'Maronda', 'Barrington', 'Pitell', 'Hemlock',
            'DRB', 'Realtor', 'The Girls', 'Scoreboard Guys', 'Sara', 'Other']
CREW = ['Tony', 'Zac', 'Anthony', 'Rick', 'Dro', 'Jon', 'Greg', 'Frank']

app = Flask(__name__)
app.secret_key = os.environ.get('WORKLOG_SECRET', 'builder-work-log')
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
IS_PG = bool(DATABASE_URL)


def connect():
    if IS_PG:
        import psycopg2
        import psycopg2.extras
        con = psycopg2.connect(DATABASE_URL)
        con.cursor_factory = psycopg2.extras.RealDictCursor
        return con
    con = sqlite3.connect(os.environ.get('WORKLOG_DB', 'worklog_local.db'))
    con.row_factory = sqlite3.Row
    return con


def run(con, sql, args=()):
    """Execute with ?-style placeholders on either backend."""
    if IS_PG:
        sql = sql.replace('?', '%s')
        cur = con.cursor()
        cur.execute(sql, args)
        return cur
    return con.execute(sql, args)


def init_db():
    con = connect()
    idcol = ('id SERIAL PRIMARY KEY' if IS_PG
             else 'id INTEGER PRIMARY KEY AUTOINCREMENT')
    blob = 'BYTEA' if IS_PG else 'BLOB'
    run(con, f"""CREATE TABLE IF NOT EXISTS jobs(
        {idcol}, date TEXT, crew TEXT, client TEXT, location TEXT, work TEXT,
        billed TEXT DEFAULT '', notes TEXT DEFAULT '', photos TEXT DEFAULT '',
        source TEXT DEFAULT 'app', created_at TEXT)""")
    run(con, f"""CREATE TABLE IF NOT EXISTS photos(
        name TEXT PRIMARY KEY, mime TEXT, data {blob})""")
    con.commit()
    con.close()


def compress(raw, ext):
    """Shrink phone photos so the database stays small."""
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((1600, 1600))
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=78)
        data = out.getvalue()
        if ext in ('.jpg', '.jpeg') and len(raw) <= len(data):
            return raw, 'image/jpeg', ext
        return data, 'image/jpeg', '.jpg'
    except Exception:
        mime = 'image/png' if ext == '.png' else 'image/jpeg'
        return raw, mime, ext


CSS = """
:root{--blue:#1f3864;--bg:#f4f6fa;--card:#fff;--line:#dde3ee;--red:#c00000;--green:#1a7f37}
*{box-sizing:border-box;margin:0}
body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--bg);color:#1a1a1a;
     padding-bottom:90px}
header{background:var(--blue);color:#fff;padding:14px 16px;display:flex;align-items:center;
       justify-content:space-between;position:sticky;top:0;z-index:5}
header h1{font-size:18px;font-weight:700}
header a{color:#cfd9ec;text-decoration:none;font-size:14px;margin-left:14px}
main{max-width:640px;margin:0 auto;padding:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:10px}
.datehdr{font-weight:700;color:var(--blue);margin:16px 4px 6px;font-size:15px}
.meta{display:flex;gap:8px;flex-wrap:wrap;font-size:13px;color:#555;margin-bottom:4px}
.tag{background:#e8edf7;color:var(--blue);border-radius:20px;padding:2px 10px;font-weight:600}
.work{font-size:15px;line-height:1.35;margin:6px 0}
.loc{font-size:14px;color:#333;font-weight:600}
.billrow{display:flex;align-items:center;justify-content:space-between;margin-top:8px}
.pill{border-radius:20px;padding:6px 14px;font-size:13px;font-weight:700;border:none}
.pill.no{background:#fde8e8;color:var(--red)}
.pill.yes{background:#e2f5e9;color:var(--green)}
.thumbs{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.thumbs img{width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.fab{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--blue);color:#fff;
     border-radius:30px;padding:16px 34px;font-size:17px;font-weight:700;text-decoration:none;
     box-shadow:0 4px 14px rgba(31,56,100,.4)}
form label{display:block;font-weight:700;font-size:13px;color:var(--blue);margin:14px 0 6px;text-transform:uppercase}
input[type=text],input[type=date],textarea,select{width:100%;padding:13px;font-size:16px;border:1px solid var(--line);
     border-radius:10px;background:#fff}
textarea{min-height:96px}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chips input{display:none}
.chips span{display:inline-block;padding:10px 16px;border:1px solid var(--line);border-radius:24px;
     background:#fff;font-size:15px}
.chips input:checked+span{background:var(--blue);color:#fff;border-color:var(--blue)}
.btn{width:100%;background:var(--blue);color:#fff;border:none;border-radius:10px;padding:16px;
     font-size:17px;font-weight:700;margin-top:18px}
.filters{display:flex;gap:8px;overflow-x:auto;padding:4px 0 8px}
.filters a{white-space:nowrap;text-decoration:none;font-size:14px;padding:8px 14px;border-radius:20px;
     background:#fff;border:1px solid var(--line);color:#333}
.filters a.on{background:var(--blue);color:#fff;border-color:var(--blue)}
.search{display:flex;gap:8px;margin-bottom:8px}
.search input{flex:1}
.search button{border:none;background:var(--blue);color:#fff;border-radius:10px;padding:0 18px;font-size:15px}
.ok{background:#e2f5e9;color:var(--green);padding:10px;border-radius:10px;font-weight:600;margin-bottom:10px}
.photoin{border:2px dashed var(--line);border-radius:10px;padding:14px;text-align:center;background:#fff}
small.hint{color:#777}
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Builder Work Log</title><style>{{css}}</style></head><body>
<header><h1>&#128736; Work Log</h1><nav>
<a href="{{url_for('index')}}">Jobs</a>
<a href="{{url_for('index', billed='No')}}">To bill</a>
<a href="{{url_for('stats')}}">Stats</a>
<a href="{{url_for('export_csv')}}">Export</a>
</nav></header><main>{{body}}</main>
{% if show_fab %}<a class="fab" href="{{url_for('new_job')}}">+ Log a job</a>{% endif %}
</body></html>"""


def page(body, show_fab=True):
    return render_template_string(PAGE, css=CSS, body=body, show_fab=show_fab)


LIST_T = """
{% if saved %}<div class="ok">&#10003; Job saved</div>{% endif %}
<form class="search" method="get" action="{{url_for('index')}}">
  <input type="text" name="q" value="{{q}}" placeholder="Search location, work, crew...">
  <button>Go</button>
</form>
<div class="filters">
  <a href="{{url_for('index')}}" class="{{'on' if not builder and billed!='No' else ''}}">All</a>
  <a href="{{url_for('index', billed='No')}}" class="{{'on' if billed=='No' else ''}}">Not billed</a>
  {% for b in builders %}
  <a href="{{url_for('index', builder=b)}}" class="{{'on' if builder==b else ''}}">{{b}}</a>
  {% endfor %}
</div>
{% for d, items in groups %}
<div class="datehdr">{{d}}</div>
  {% for j in items %}
  <div class="card">
    <div class="meta">
      {% if j['client'] %}<span class="tag">{{j['client']}}</span>{% endif %}
      {% if j['crew'] %}<span>&#128101; {{j['crew']}}</span>{% endif %}
    </div>
    {% if j['location'] %}<div class="loc">&#128205; {{j['location']}}</div>{% endif %}
    {% if j['work'] %}<div class="work">{{j['work']}}</div>{% endif %}
    {% if j['photolist'] %}<div class="thumbs">
      {% for p in j['photolist'] %}<a href="{{url_for('photo', name=p)}}"><img src="{{url_for('photo', name=p)}}"></a>{% endfor %}
    </div>{% endif %}
    <div class="billrow">
      <form method="post" action="{{url_for('toggle_billed', job_id=j['id'])}}">
        {% if j['billed'] == 'Yes' %}<button class="pill yes">Billed &#10003;</button>
        {% else %}<button class="pill no">Not billed — tap when billed</button>{% endif %}
      </form>
      <a href="{{url_for('edit_job', job_id=j['id'])}}" style="font-size:13px">Edit</a>
    </div>
  </div>
  {% endfor %}
{% endfor %}
{% if not groups %}<div class="card">No jobs match.</div>{% endif %}
{% if more %}<div style="text-align:center;margin:14px"><a href="{{more}}">Show more</a></div>{% endif %}
"""

FORM_T = """
<form method="post" enctype="multipart/form-data">
<label>Date</label>
<input type="date" name="date" value="{{j['date']}}" required>
<label>Crew — tap everyone who was there</label>
<div class="chips">
  {% for c in crew %}
  <label style="margin:0;text-transform:none"><input type="checkbox" name="crew" value="{{c}}"
    {{'checked' if c in j['crewlist'] else ''}}><span>{{c}}</span></label>
  {% endfor %}
</div>
<input type="text" name="crew_other" value="{{j['crew_other']}}" placeholder="Anyone else..." style="margin-top:8px">
<label>Builder / Client</label>
<select name="client">
  <option value=""></option>
  {% for b in builders %}<option {{'selected' if j['client']==b else ''}}>{{b}}</option>{% endfor %}
</select>
<input type="text" name="client_other" value="{{j['client_other']}}" placeholder="Or type a one-off customer" style="margin-top:8px">
<label>Location / Community</label>
<input type="text" name="location" value="{{j['location']}}" placeholder="Community name or address">
<label>Work performed</label>
<textarea name="work" placeholder="What did you do?">{{j['work']}}</textarea>
<label>Photos</label>
<div class="photoin">
  <input type="file" name="photos" accept="image/*" capture="environment" multiple>
  <div><small class="hint">Take pictures or pick from gallery — saved with the job automatically</small></div>
</div>
{% if j['photolist'] %}<div class="thumbs">
  {% for p in j['photolist'] %}<img src="{{url_for('photo', name=p)}}">{% endfor %}
</div>{% endif %}
<label>Billed in UpSignDown?</label>
<div class="chips">
  <label style="margin:0;text-transform:none"><input type="radio" name="billed" value="" {{'checked' if j['billed']=='' else ''}}><span>Not yet</span></label>
  <label style="margin:0;text-transform:none"><input type="radio" name="billed" value="No" {{'checked' if j['billed']=='No' else ''}}><span>Needs billed</span></label>
  <label style="margin:0;text-transform:none"><input type="radio" name="billed" value="Yes" {{'checked' if j['billed']=='Yes' else ''}}><span>Billed</span></label>
</div>
<button class="btn">Save job</button>
</form>
"""

PIN_T = """
<div class="card" style="margin-top:40px">
<form method="post">
<label>Enter crew PIN</label>
<input type="text" name="pin" inputmode="numeric" autofocus>
<button class="btn">Enter</button>
</form></div>
"""

STATS_T = """
<div class="card"><div class="datehdr" style="margin-top:0">This month</div>
<div class="work">{{m}} jobs logged</div></div>
<div class="card"><div class="datehdr" style="margin-top:0">This year</div>
<div class="work">{{y}} jobs logged</div></div>
<div class="card"><div class="datehdr" style="margin-top:0;color:var(--red)">Needs billed</div>
<div class="work">{{nb}} jobs — <a href="{{url_for('index', billed='No')}}">see the list</a></div></div>
<div class="card"><div class="datehdr" style="margin-top:0">Jobs by builder ({{year}})</div>
<table style="width:100%;font-size:15px;border-collapse:collapse">
{% for b, n in per_builder %}
<tr><td style="padding:6px 0;border-bottom:1px solid var(--line)">{{b}}</td>
<td style="text-align:right;border-bottom:1px solid var(--line);font-weight:700">{{n}}</td></tr>
{% endfor %}</table></div>
"""


@app.before_request
def require_pin():
    if not PIN or request.endpoint in ('pin', 'static'):
        return
    if session.get('ok') != PIN:
        return redirect(url_for('pin'))


@app.route('/pin', methods=['GET', 'POST'])
def pin():
    if request.method == 'POST':
        if request.form.get('pin', '') == PIN:
            session['ok'] = PIN
            session.permanent = True
            return redirect(url_for('index'))
    return page(render_template_string(PIN_T), show_fab=False)


@app.route('/')
def index():
    q = request.args.get('q', '').strip()
    builder = request.args.get('builder', '')
    billed = request.args.get('billed', '')
    limit = min(int(request.args.get('limit', 120)), 2000)
    con = connect()
    sql = "SELECT * FROM jobs WHERE 1=1"
    args = []
    if q:
        sql += " AND (location LIKE ? OR work LIKE ? OR crew LIKE ? OR client LIKE ?)"
        args += [f'%{q}%'] * 4
    if builder:
        sql += " AND client=?"
        args.append(builder)
    if billed:
        sql += " AND billed=?"
        args.append(billed)
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    args.append(limit + 1)
    rows = [dict(r) for r in run(con, sql, args).fetchall()]
    con.close()
    more = None
    if len(rows) > limit:
        rows = rows[:limit]
        a = dict(request.args)
        a['limit'] = limit * 2
        more = url_for('index', **a)
    groups = []
    for r in rows:
        r['photolist'] = [p for p in (r['photos'] or '').split(';') if p.strip()]
        d = r['date'] or 'No date'
        if d != 'No date':
            try:
                d = datetime.date.fromisoformat(d).strftime('%a %b %d, %Y')
            except ValueError:
                pass
        if not groups or groups[-1][0] != d:
            groups.append((d, []))
        groups[-1][1].append(r)
    body = render_template_string(LIST_T, groups=groups, builders=BUILDERS[:8],
                                  q=q, builder=builder, billed=billed,
                                  saved=request.args.get('saved'), more=more)
    return page(body)


def save_photos(con, files, date):
    names = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower() or '.jpg'
        if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.heic'):
            continue
        data, mime, ext = compress(f.read(), ext)
        i = 1
        while True:
            name = f"{date}_{i:03d}{ext}"
            if not run(con, "SELECT 1 FROM photos WHERE name=?", (name,)).fetchone():
                break
            i += 1
        run(con, "INSERT INTO photos(name, mime, data) VALUES(?,?,?)",
            (name, mime, data))
        names.append(name)
    return names


def form_to_job(con, form, files, existing_photos=''):
    crew = list(form.getlist('crew'))
    other = form.get('crew_other', '').strip()
    if other:
        crew += [re.sub(r'\s+', ' ', x).strip().title() for x in re.split(r'[/,]', other) if x.strip()]
    client = form.get('client_other', '').strip() or form.get('client', '').strip()
    date = form.get('date') or datetime.date.today().isoformat()
    photos = [p for p in existing_photos.split(';') if p.strip()]
    photos += save_photos(con, files.getlist('photos'), date)
    return {
        'date': date,
        'crew': '/'.join(dict.fromkeys(crew)),
        'client': client,
        'location': form.get('location', '').strip(),
        'work': form.get('work', '').strip(),
        'billed': form.get('billed', ''),
        'photos': ';'.join(photos),
    }


EMPTY = {'date': '', 'crewlist': [], 'crew_other': '', 'client': '',
         'client_other': '', 'location': '', 'work': '', 'billed': '',
         'photolist': []}


@app.route('/new', methods=['GET', 'POST'])
def new_job():
    if request.method == 'POST':
        con = connect()
        j = form_to_job(con, request.form, request.files)
        run(con,
            "INSERT INTO jobs(date,crew,client,location,work,billed,photos,source,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (j['date'], j['crew'], j['client'], j['location'], j['work'],
             j['billed'], j['photos'], 'app',
             datetime.datetime.now().isoformat(timespec='seconds')))
        con.commit()
        con.close()
        return redirect(url_for('index', saved=1))
    j = dict(EMPTY, date=datetime.date.today().isoformat())
    return page(render_template_string(FORM_T, j=j, crew=CREW, builders=BUILDERS),
                show_fab=False)


@app.route('/edit/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    con = connect()
    row = run(con, "SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        con.close()
        return redirect(url_for('index'))
    if request.method == 'POST':
        j = form_to_job(con, request.form, request.files,
                        existing_photos=row['photos'] or '')
        run(con,
            "UPDATE jobs SET date=?,crew=?,client=?,location=?,work=?,billed=?,photos=? WHERE id=?",
            (j['date'], j['crew'], j['client'], j['location'], j['work'],
             j['billed'], j['photos'], job_id))
        con.commit()
        con.close()
        return redirect(url_for('index', saved=1))
    r = dict(row)
    con.close()
    known = set(CREW)
    crewlist = (r['crew'] or '').split('/')
    j = {
        'date': r['date'] or '',
        'crewlist': [c for c in crewlist if c in known],
        'crew_other': '/'.join(c for c in crewlist if c and c not in known),
        'client': r['client'] if r['client'] in BUILDERS else '',
        'client_other': '' if r['client'] in BUILDERS else (r['client'] or ''),
        'location': r['location'] or '',
        'work': r['work'] or '',
        'billed': r['billed'] or '',
        'photolist': [p for p in (r['photos'] or '').split(';') if p.strip()],
    }
    return page(render_template_string(FORM_T, j=j, crew=CREW, builders=BUILDERS),
                show_fab=False)


@app.route('/billed/<int:job_id>', methods=['POST'])
def toggle_billed(job_id):
    con = connect()
    row = run(con, "SELECT billed FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row:
        new = 'No' if row['billed'] == 'Yes' else 'Yes'
        run(con, "UPDATE jobs SET billed=? WHERE id=?", (new, job_id))
        con.commit()
    con.close()
    return redirect(request.referrer or url_for('index'))


@app.route('/photo/<path:name>')
def photo(name):
    con = connect()
    row = run(con, "SELECT mime, data FROM photos WHERE name=?", (name,)).fetchone()
    con.close()
    if not row:
        abort(404)
    return Response(bytes(row['data']), mimetype=row['mime'] or 'image/jpeg',
                    headers={'Cache-Control': 'public, max-age=31536000'})


@app.route('/stats')
def stats():
    con = connect()
    year = datetime.date.today().year
    month_start = datetime.date.today().replace(day=1).isoformat()
    year_start = f'{year}-01-01'
    m = run(con, "SELECT COUNT(*) c FROM jobs WHERE date>=?", (month_start,)).fetchone()['c']
    y = run(con, "SELECT COUNT(*) c FROM jobs WHERE date>=?", (year_start,)).fetchone()['c']
    nb = run(con, "SELECT COUNT(*) c FROM jobs WHERE billed='No'").fetchone()['c']
    per_builder = run(con,
        "SELECT client, COUNT(*) n FROM jobs WHERE date>=? AND client<>''"
        " GROUP BY client ORDER BY n DESC LIMIT 15", (year_start,)).fetchall()
    con.close()
    body = render_template_string(STATS_T, m=m, y=y, nb=nb, year=year,
                                  per_builder=[(r['client'], r['n']) for r in per_builder])
    return page(body)


@app.route('/export.csv')
def export_csv():
    con = connect()
    rows = run(con, "SELECT * FROM jobs ORDER BY date, id").fetchall()
    con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Crew', 'Builder/Client', 'Location', 'Work Performed',
                'Billed', 'Notes', 'Photos', 'Source'])
    for r in rows:
        w.writerow([r['date'], r['crew'], r['client'], r['location'], r['work'],
                    r['billed'], r['notes'], r['photos'], r['source']])
    return Response(
        '﻿' + buf.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=work_log_export.csv'})


@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    """One-time import of the migrated history (PIN-protected like the rest)."""
    con = connect()
    n = run(con, "SELECT COUNT(*) c FROM jobs").fetchone()['c']
    if request.method == 'POST':
        if n > 100:
            con.close()
            return page('<div class="card">Import blocked: this database already '
                        f'has {n} jobs. Import is only for a fresh database.</div>',
                        show_fab=False)
        f = request.files.get('csv')
        if not f:
            con.close()
            return redirect(url_for('import_csv'))
        text = f.read().decode('utf-8-sig')
        added = 0
        for r in csv.DictReader(io.StringIO(text)):
            run(con,
                "INSERT INTO jobs(date,crew,client,location,work,billed,notes,photos,source,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (r.get('Date', ''), r.get('Crew', ''), r.get('Builder/Client', ''),
                 r.get('Location', ''), r.get('Work Performed', ''),
                 r.get('Billed', ''), r.get('Notes', ''), '',
                 r.get('Source', 'migrated') or 'migrated',
                 datetime.datetime.now().isoformat(timespec='seconds')))
            added += 1
        con.commit()
        con.close()
        return page(f'<div class="ok">&#10003; Imported {added} jobs.</div>',
                    show_fab=False)
    con.close()
    return page(f"""<div class="card">
      <div class="datehdr" style="margin-top:0">Import history (one time)</div>
      <div class="work">Database currently has {n} jobs.</div>
      <form method="post" enctype="multipart/form-data">
        <input type="file" name="csv" accept=".csv">
        <button class="btn">Import CSV</button>
      </form></div>""", show_fab=False)


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5078)), debug=False)
