import os
import time

import psycopg2

from rules import DEFAULT_LINE, SEASONS, weigh


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
    # 季节放行线：每一季一条当前线
    cur.execute(
        """CREATE TABLE IF NOT EXISTS season_lines (
            season text PRIMARY KEY,
            line double precision NOT NULL,
            changed_by text NOT NULL,
            changed_at timestamp with time zone NOT NULL DEFAULT now()
        )"""
    )
    # 改线履历：只追加，旧行永不更新
    cur.execute(
        """CREATE TABLE IF NOT EXISTS season_line_history (
            id serial PRIMARY KEY,
            season text NOT NULL,
            old_line double precision,
            new_line double precision NOT NULL,
            changed_by text NOT NULL,
            changed_at timestamp with time zone NOT NULL DEFAULT now()
        )"""
    )

    # 老库平滑升级：cuppings 补 season 列
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='cuppings' AND column_name='season'")
    if cur.fetchone() is None:
        cur.execute("ALTER TABLE cuppings ADD COLUMN season text")

    # 四季各一条放行线，缺哪季补哪季，默认 7
    for season in SEASONS:
        cur.execute(
            "INSERT INTO season_lines (season, line, changed_by) VALUES (%s,%s,%s) ON CONFLICT (season) DO NOTHING",
            (season, DEFAULT_LINE, "seed"),
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

    # 历史落库行若没有季节，按批次名首字回填
    cur.execute("SELECT id, lot FROM cuppings WHERE season IS NULL")
    for row_id, lot in cur.fetchall():
        season = next((s for s in SEASONS if lot.startswith(s)), None)
        if season:
            cur.execute("UPDATE cuppings SET season=%s WHERE id=%s", (season, row_id))

    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
