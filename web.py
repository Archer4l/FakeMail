import sqlite3,os
from contextlib import contextmanager
from flask import abort
from flask import make_response
from flask import Flask, jsonify, redirect, url_for, request
from flask import render_template

app = Flask(__name__)
app.json.ensure_ascii = False

DB = os.path.expanduser("~/mailbox/fake_mail.db")
TABLE = "fake_mail"
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
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    app.run("127.0.0.1", "9080", debug=True)
