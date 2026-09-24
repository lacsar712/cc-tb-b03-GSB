import os
from functools import wraps

import psycopg2
from flask import Flask, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from rules import weigh

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "tea-cupping-dev-secret")

ACCOUNTS = {
    "taster": {"password": "tea123456", "role": "writer"},
    "observer": {"password": "look123456", "role": "reader"},
}

SEASONS = ("春", "夏", "秋", "冬")


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
    season = request.form.get("season", "").strip()
    if season not in SEASONS:
        return ("交评必须声明季节（春/夏/秋/冬）", 400)
    aroma = float(request.form["aroma"])
    taste = float(request.form["taste"])
    liquor = float(request.form["liquor"])
    lot = request.form["lot"].strip()
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 服务端用对应季节线判定
        cur.execute("SELECT line_value FROM season_lines WHERE season = %s", (season,))
        line_row = cur.fetchone()
        line = float(line_row["line_value"])
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
        cur.execute("SELECT * FROM season_lines")
        lines = cur.fetchall()
        # 季节主键没有天然四季次序，按春→冬展示
        order = {s: i for i, s in enumerate(SEASONS)}
        lines.sort(key=lambda r: order.get(r["season"], 99))
        cur.execute(
            """SELECT * FROM season_line_history ORDER BY id DESC"""
        )
        history = cur.fetchall()
    return render_template(
        "seasons.html",
        lines=lines,
        history=history,
        seasons=SEASONS,
        can_write=session.get("role") == "writer",
    )


@app.post("/seasons/lines")
@login_required
def update_line():
    if session.get("role") != "writer":
        return ("仅审评员可调整放行线", 403)
    season = request.form.get("season", "").strip()
    if season not in SEASONS:
        return ("无效的季节档", 400)
    new_line = float(request.form["line"])
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT line_value FROM season_lines WHERE season = %s FOR UPDATE",
            (season,),
        )
        row = cur.fetchone()
        old_line = float(row["line_value"])
        if new_line != old_line:
            # 履历只追加：旧行不被后续修改覆盖；历史审评结论也不改写
            cur.execute(
                """INSERT INTO season_line_history
                       (season, old_line, new_line, changed_by)
                   VALUES (%s, %s, %s, %s)""",
                (season, old_line, new_line, session["user"]),
            )
            cur.execute(
                """UPDATE season_lines
                       SET line_value = %s, updated_by = %s, updated_at = now()
                     WHERE season = %s""",
                (new_line, session["user"], season),
            )
        conn.commit()
    return redirect(url_for("seasons_page"))
