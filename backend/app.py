import os
from functools import wraps

import psycopg2
from flask import Flask, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from rules import SEASONS, weigh

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "tea-cupping-dev-secret")

ACCOUNTS = {
    "taster": {"password": "tea123456", "role": "writer"},
    "observer": {"password": "look123456", "role": "reader"},
}


def db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def login_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrap


@app.get("/health")
def health():
    return {"status": "ok", "service": "tea-blend-cupping"}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        name = request.form.get("username", "").strip()
        account = ACCOUNTS.get(name)
        if not account or account["password"] != request.form.get("password", ""):
            error = "用户名或密码错误"
        else:
            session["user"] = name
            session["role"] = account["role"]
            return redirect(url_for("home"))
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def home():
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM cuppings ORDER BY id DESC")
        rows = cur.fetchall()
    return render_template(
        "home.html",
        rows=rows,
        seasons=SEASONS,
        can_write=session.get("role") == "writer",
    )


@app.post("/cuppings")
@login_required
def create():
    if session.get("role") != "writer":
        return ("仅审评员可提交拼配审评", 403)
    # 交评必须声明季节，缺声明直接拒交
    season = (request.form.get("season") or "").strip()
    if season not in SEASONS:
        return ("交评必须声明季节（春/夏/秋/冬）", 400)
    aroma = float(request.form["aroma"])
    taste = float(request.form["taste"])
    liquor = float(request.form["liquor"])
    lot = request.form["lot"].strip()
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 服务端用声明季节对应的当前线判定
        cur.execute("SELECT line FROM season_lines WHERE season=%s", (season,))
        line_row = cur.fetchone()
        if line_row is None:
            return (f"未知季节档：{season}", 400)
        line = line_row["line"]
        verdict, note, score = weigh(aroma, taste, liquor, line)
        cur.execute(
            """INSERT INTO cuppings (lot, season, aroma, taste, liquor, score, verdict, note, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (lot, season, aroma, taste, liquor, score, verdict, note, session["user"]),
        )
        row = cur.fetchone()
        conn.commit()
    if request.headers.get("HX-Request"):
        return render_template("_row.html", row=row)
    return redirect(url_for("home"))


@app.get("/seasons")
@login_required
def seasons_page():
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM season_lines ORDER BY array_position(ARRAY['春','夏','秋','冬'], season)")
        lines = cur.fetchall()
        cur.execute(
            """SELECT * FROM season_line_history
               ORDER BY id DESC"""
        )
        history = cur.fetchall()
    return render_template(
        "seasons.html",
        lines=lines,
        history=history,
        can_write=session.get("role") == "writer",
    )


@app.post("/seasons/<season>/line")
@login_required
def update_line(season):
    if session.get("role") != "writer":
        return ("仅审评员可调整季节放行线", 403)
    if season not in SEASONS:
        return (f"未知季节档：{season}", 400)
    try:
        new_line = float(request.form["line"])
    except (KeyError, TypeError, ValueError):
        return ("放行线必须是数字", 400)

    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT line FROM season_lines WHERE season=%s FOR UPDATE", (season,))
        row = cur.fetchone()
        if row is None:
            return (f"未知季节档：{season}", 400)
        old_line = row["line"]
        if new_line == old_line:
            conn.rollback()
        else:
            cur.execute(
                "UPDATE season_lines SET line=%s, changed_by=%s, changed_at=now() WHERE season=%s",
                (new_line, session["user"], season),
            )
            # 履历只追加：旧行不被后续修改覆盖
            cur.execute(
                """INSERT INTO season_line_history (season, old_line, new_line, changed_by)
                   VALUES (%s,%s,%s,%s)""",
                (season, old_line, new_line, session["user"]),
            )
            conn.commit()
    return redirect(url_for("seasons_page"))
