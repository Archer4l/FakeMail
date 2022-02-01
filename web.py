import sqlite3,os
from flask import abort
from flask import make_response
from flask import Flask, jsonify, redirect, url_for, request
from flask import render_template

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

DB = os.path.expanduser("~/mailbox/fake_mail.db")
TABLE = "fake_mail"

def deletemail(id):
    if id.isnumeric():
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        sql = f"delete from {TABLE} where id = %s" % request.form["deletemail"]
        cur.execute(sql)
        cur.close()
        conn.commit()
        conn.close()

@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST' and 'deletemail' in request.form:
       deletemail(request.form["deletemail"])

    curpage=1
    offset=0
    limit=12

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(f"select count(*) from {TABLE}")
    rowcount=int(cur.fetchone()[0])
    totalpage=(rowcount // limit  )
    if totalpage*limit < rowcount:
        totalpage = (rowcount // limit + 1 )

    if request.method:
        if request.args.get('page'):
            if request.args.get('page').isnumeric():
                curpage=int(request.args.get('page'))
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

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    sql = f"""
            select id, email_title, email_from, email_to, dt, has_attach from {TABLE}  order by id desc  LIMIT {limit} OFFSET {offset}
        """
    cur.execute(sql)
    val = cur.fetchall()
    cur.close()
    conn.close()


    return render_template("index.html", mails=val, curpage=curpage, totalpage=totalpage, startpage=startpage, endpage=endpage)

@app.route('/search', methods=['GET','POST'])
def search():

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    if request.method=='POST' and 'search' in request.form:
        if 'deletemail' in request.form:
            deletemail(request.form["deletemail"])
        search="%"+request.form['search']+"%"
        sql = f"select id, email_title, email_from, email_to, dt, has_attach from {TABLE}  WHERE email_title LIKE '%s' order by id desc limit 500" % search
        cur.execute(sql)
        val = cur.fetchall()
        cur.close()
        conn.close()
        return render_template("index.html", mails=val)
    else:
        return redirect("/")


@app.route('/delete_all', methods=['GET'])
def delete_all():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    sql = f"""
                    delete from {TABLE} 
                """
    cur.execute(sql)
    cur.close()
    conn.commit()
    conn.close()
    return redirect("/")

@app.route('/delete/<int:id>', methods=['GET'])
def delete(id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    sql = f"delete from {TABLE} where id = %s" % id
    cur.execute(sql)
    cur.close()
    conn.commit()
    conn.close()
    return redirect("/")


@app.route('/email/<path:email>', methods=['GET'])
def email(email):
    """
    get mail by to email
    :param email:
    :param type:
    :return:
    """
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    sql = f"select id,dt,email_raw,email_from, email_to, email_title from {TABLE}  where email_to=? order by id desc limit 1;"
    cur.execute(sql, [email])
    val = cur.fetchone()
    cur.close()
    conn.close()
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
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        sql = f"select email_raw from {TABLE}  where id=%s" % email_id

        cur.execute(sql)
        val = cur.fetchone()
        cur.close()
        conn.close()
        raw_email = val[0]
        response = make_response(raw_email)
        response.headers.set('Content-Type', 'message/rfc822')
        response.headers.set('Content-Disposition', 'attachment', filename='%s.eml' % email_id)
        return response
    except Exception as err:
        print(err)
        abort(404)

def start_web(host, port):
    app.run(host, port)

if __name__=="__main__":
    app.run("127.0.0.1", "9080", debug=True)
