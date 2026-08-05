import sqlite3, os
from contextlib import contextmanager
from flask import abort
from flask import make_response
from flask import Flask, jsonify, redirect, url_for, request
from flask import render_template

app = Flask(__name__)
app.json.ensure_ascii = False

DB = os.path.expanduser("~/mailbox/fake_mail.db")
TABLE = "fake_mail"

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

def deletemail(id):
    id = to_int(id)
    if id is None:
        return
    with connect() as conn:
        conn.execute(f"delete from {TABLE} where id = ?", (id,))

@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST' and 'deletemail' in request.form:
       deletemail(request.form["deletemail"])

    curpage=1
    offset=0
    limit=12

    with connect() as conn:
        cur = conn.execute(f"select count(*) from {TABLE}")
        rowcount=int(cur.fetchone()[0])
        totalpage=(rowcount // limit  )
        if totalpage*limit < rowcount:
            totalpage = (rowcount // limit + 1 )

        page = to_int(request.args.get('page'))
        if page is not None:
            curpage = page
            offset = limit * curpage - limit

        if curpage > totalpage:
            curpage = totalpage
            offset = limit * curpage - limit

        startpage = curpage - limit//2
        endpage = curpage + limit//2

        if startpage < 1:
            startpage = 1
            endpage=limit+1
        elif startpage > 1 and totalpage+1-curpage <= limit//2:
            endpage=totalpage+1
            startpage=totalpage+1 - limit

        if limit>=totalpage:
            startpage = 1
            endpage = totalpage +1

        sql = f"""
                select id, email_title, email_from, email_to, dt, has_attach from {TABLE}  order by id desc  LIMIT ? OFFSET ?
            """
        cur = conn.execute(sql, (limit, offset))
        val = cur.fetchall()

    return render_template("index.html", mails=val, curpage=curpage, totalpage=totalpage, startpage=startpage, endpage=endpage)

@app.route('/search', methods=['GET','POST'])
def search():

    if request.method=='POST' and 'search' in request.form:
        if 'deletemail' in request.form:
            deletemail(request.form["deletemail"])
        search="%"+like_escape(request.form['search'])+"%"
        sql = f"select id, email_title, email_from, email_to, dt, has_attach from {TABLE}  WHERE email_title LIKE ? ESCAPE '\\' order by id desc limit 500"
        with connect() as conn:
            cur = conn.execute(sql, (search,))
            val = cur.fetchall()
        return render_template("index.html", mails=val)
    else:
        return redirect("/")


@app.route('/delete_all', methods=['GET'])
def delete_all():
    with connect() as conn:
        conn.execute(f"delete from {TABLE}")
    return redirect("/")

@app.route('/delete/<int:id>', methods=['GET'])
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
    raw_email = val[2]
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
    response = make_response(val[0])
    response.headers.set('Content-Type', 'message/rfc822')
    response.headers.set('Content-Disposition', 'attachment', filename='%s.eml' % email_id)
    return response

def start_web(host, port):
    app.run(host, port)

if __name__=="__main__":
    app.run("127.0.0.1", "9080", debug=True)
