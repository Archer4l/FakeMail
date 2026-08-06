import sqlite3,os
from contextlib import contextmanager
from email import message_from_bytes, policy
from flask import abort
from flask import make_response
from flask import Flask, jsonify, redirect, url_for, request
from flask import render_template

app = Flask(__name__)
app.json.ensure_ascii = False

MAILBOX = os.path.expanduser(os.environ.get('FAKEMAIL_DIR', "~/mailbox"))
DB = os.path.join(MAILBOX, "fake_mail.db")
TABLE = "fake_mail"
WEB_HOST = os.environ.get('FAKEMAIL_WEB_HOST', "127.0.0.1")
WEB_PORT = int(os.environ.get('FAKEMAIL_WEB_PORT', 9080))
PAGE_SIZE = 25
PAGER_LINKS = 9

@contextmanager
def connect():
    conn = sqlite3.connect(DB)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def like_escape(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def raw_bytes(value):
    return value if isinstance(value, bytes) else value.encode('utf8', 'replace')

def raw_text(value):
    return value if isinstance(value, str) else value.decode('utf8', 'replace')

def load_message(email_id):
    sql = f"select id, email_title, email_from, email_to, dt, email_raw from {TABLE} where id=?"
    with connect() as conn:
        cur = conn.execute(sql, (email_id,))
        val = cur.fetchone()
    if val is None:
        abort(404)
    raw = raw_bytes(val[5])
    try:
        return val, message_from_bytes(raw, policy=policy.default)
    except Exception:
        return val, None

def part_text(part):
    try:
        return part.get_content()
    except Exception as err:
        return f"[cannot decode this part: {err}]"

def part_size(part):
    payload = part.get_payload(decode=True) or b""
    size = len(payload)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size = size / 1024

def attachment_name(part, idx):
    name = os.path.basename(part.get_filename() or "")
    name = "".join(c for c in name if c.isprintable() and c not in '"\\/')
    return name or f"part{idx}"

def page_window(curpage, totalpage, links=PAGER_LINKS):
    """first and last+1 page number to show in the pager"""
    start = max(1, min(curpage - links // 2, totalpage - links + 1))
    return start, min(totalpage, start + links - 1) + 1

def deletemail(id):
    id = to_int(id)
    if id is None:
        return
    with connect() as conn:
        conn.execute(f"delete from {TABLE} where id = ?", (id,))

@app.route('/', methods=['GET','POST'])
def index():
    query = request.args.get('q', '').strip()

    if request.method == 'POST' and 'deletemail' in request.form:
        deletemail(request.form["deletemail"])
        return redirect(url_for('index', q=query or None, page=request.args.get('page')))

    where, params = "", []
    if query:
        where = "where email_title like ? escape '\\'"
        params = ["%" + like_escape(query) + "%"]

    with connect() as conn:
        rowcount = conn.execute(f"select count(*) from {TABLE} {where}", params).fetchone()[0]
        totalpage = rowcount // PAGE_SIZE
        if totalpage * PAGE_SIZE < rowcount:
            totalpage += 1
        if totalpage < 1:
            totalpage = 1

        curpage = min(max(to_int(request.args.get('page'), 1), 1), totalpage)
        startpage, endpage = page_window(curpage, totalpage)

        sql = f"""
                select id, email_title, email_from, email_to, dt, has_attach from {TABLE} {where} order by id desc limit ? offset ?
            """
        val = conn.execute(sql, params + [PAGE_SIZE, (curpage - 1) * PAGE_SIZE]).fetchall()

    return render_template("index.html", mails=val, query=query, rowcount=rowcount,
                           curpage=curpage, totalpage=totalpage, startpage=startpage, endpage=endpage)

@app.route('/search', methods=['GET','POST'])
def search():
    query = request.form.get('search') or request.args.get('search') or request.args.get('q')
    return redirect(url_for('index', q=query or None))


@app.route('/delete_all', methods=['POST'])
def delete_all():
    with connect() as conn:
        conn.execute(f"delete from {TABLE}")
    return redirect("/")

@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    with connect() as conn:
        conn.execute(f"delete from {TABLE} where id = ?", (id,))
    return redirect("/")


@app.route('/message/<int:email_id>', methods=['GET'])
def message(email_id):
    val, msg = load_message(email_id)
    if msg is None:
        return render_template("message.html", mail=val, headers=[], plain=raw_text(val[5]),
                               has_html=False, attachments=[])

    headers = [(name, msg[name]) for name in ('From', 'To', 'Cc', 'Subject', 'Date') if msg[name]]
    plain = msg.get_body(preferencelist=('plain',))
    attachments = [{'idx': i, 'name': attachment_name(part, i),
                    'type': part.get_content_type(), 'size': part_size(part)}
                   for i, part in enumerate(msg.iter_attachments())]

    return render_template("message.html", mail=val, headers=headers,
                           plain=part_text(plain) if plain else None,
                           has_html=msg.get_body(preferencelist=('html',)) is not None,
                           attachments=attachments)


@app.route('/message/<int:email_id>/html', methods=['GET'])
def message_html(email_id):
    val, msg = load_message(email_id)
    part = msg.get_body(preferencelist=('html',)) if msg else None
    if part is None:
        abort(404)
    response = make_response(part_text(part))
    response.headers.set('Content-Type', 'text/html; charset=utf-8')
    # opaque origin, no network, no scripts: mail bodies are untrusted input
    response.headers.set('Content-Security-Policy',
                         "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'")
    response.headers.set('X-Content-Type-Options', 'nosniff')
    return response


@app.route('/message/<int:email_id>/attachment/<int:idx>', methods=['GET'])
def attachment(email_id, idx):
    val, msg = load_message(email_id)
    parts = list(msg.iter_attachments()) if msg else []
    if idx >= len(parts):
        abort(404)
    response = make_response(parts[idx].get_payload(decode=True) or b"")
    response.headers.set('Content-Type', 'application/octet-stream')
    response.headers.set('X-Content-Type-Options', 'nosniff')
    response.headers.set('Content-Disposition', 'attachment',
                         filename=attachment_name(parts[idx], idx))
    return response


@app.route('/email/<path:email>', methods=['GET'])
def email(email):
    """
    get mail by to email
    :param email:
    :param type:
    :return:
    """
    sql = f"select id,dt,email_raw,email_from, email_to, email_title from {TABLE}  where email_to=? order by id desc limit 1;"
    with connect() as conn:
        cur = conn.execute(sql, [email])
        val = cur.fetchone()
    if val is None:
        abort(404)
    raw_email = raw_text(val[2])
    result = {}
    result['id'] = val[0]
    result['from'] = val[3]
    result['to_'] = val[4]
    result['title'] = val[5]
    result['dt'] = val[1]
    result['raw'] = raw_email
    return jsonify(result)


@app.route('/raw_mail/<int:email_id>', methods=['GET'])
def raw_mail(email_id):
    sql = f"select email_raw from {TABLE}  where id=?"
    with connect() as conn:
        cur = conn.execute(sql, (email_id,))
        val = cur.fetchone()
    if val is None:
        abort(404)
    response = make_response(raw_bytes(val[0]))
    response.headers.set('Content-Type', 'message/rfc822')
    response.headers.set('Content-Disposition', 'attachment', filename='%s.eml' % email_id)
    return response

def start_web(host, port):
    app.run(host, port)

if __name__=="__main__":
    os.makedirs(MAILBOX, exist_ok=True)
    app.run(WEB_HOST, WEB_PORT, debug=True)
