import os
import time

import psycopg2

from rules import weigh

SEASONS = ("春", "夏", "秋", "冬")
DEFAULT_LINE = 7.0


def connect():
    last = None
    for _ in range(30):
        try:
            return psycopg2.connect(os.environ["DATABASE_URL"])
        except psycopg2.OperationalError as exc:
            last = exc
            time.sleep(1)
    raise last


def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS cuppings (
            id serial PRIMARY KEY,
            lot text NOT NULL,
            aroma double precision NOT NULL,
            taste double precision NOT NULL,
            liquor double precision NOT NULL,
            score double precision NOT NULL,
            verdict text NOT NULL,
            note text NOT NULL,
            created_by text NOT NULL
        )"""
    )
    # 季节档：交评时声明的季节，老数据按批次名补档
    cur.execute("ALTER TABLE cuppings ADD COLUMN IF NOT EXISTS season text")

    # 四季放行线表：每季一条当前线
    cur.execute(
        """CREATE TABLE IF NOT EXISTS season_lines (
            season text PRIMARY KEY,
            line_value double precision NOT NULL,
            updated_by text NOT NULL DEFAULT 'system',
            updated_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    # 改线履历：只追加，旧行永不被覆盖
    cur.execute(
        """CREATE TABLE IF NOT EXISTS season_line_history (
            id serial PRIMARY KEY,
            season text NOT NULL,
            old_line double precision NOT NULL,
            new_line double precision NOT NULL,
            changed_by text NOT NULL,
            changed_at timestamptz NOT NULL DEFAULT now()
        )"""
    )

    for season in SEASONS:
        cur.execute(
            "INSERT INTO season_lines (season, line_value) VALUES (%s, %s) ON CONFLICT (season) DO NOTHING",
            (season, DEFAULT_LINE),
        )

    cur.execute("SELECT COUNT(*) FROM cuppings")
    if cur.fetchone()[0] == 0:
        for lot, season, aroma, taste, liquor in (
            ("春茶-A", "春", 8, 8, 7),
            ("夏茶-C", "夏", 5, 4, 6),
        ):
            verdict, note, score = weigh(aroma, taste, liquor, DEFAULT_LINE)
            cur.execute(
                """INSERT INTO cuppings (lot, season, aroma, taste, liquor, score, verdict, note, created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (lot, season, aroma, taste, liquor, score, verdict, note, "taster"),
            )

    cur.execute("UPDATE cuppings SET season = '春' WHERE season IS NULL AND lot LIKE %s", ("春%",))
    cur.execute("UPDATE cuppings SET season = '夏' WHERE season IS NULL AND lot LIKE %s", ("夏%",))
    cur.execute("UPDATE cuppings SET season = '秋' WHERE season IS NULL AND lot LIKE %s", ("秋%",))
    cur.execute("UPDATE cuppings SET season = '冬' WHERE season IS NULL AND lot LIKE %s", ("冬%",))

    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
