import sqlite3
from datetime import datetime, timedelta, timezone

from flask import current_app, g

TAIPEI = timezone(timedelta(hours=8))


def now():
    return datetime.now(TAIPEI).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS case_counters (
            day TEXT PRIMARY KEY, next_value INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY,
            case_number TEXT NOT NULL UNIQUE,
            submission_token TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK(kind IN ('feedback','complaint','human')),
            name TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            organization TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            event_time TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            people TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            evidence_note TEXT NOT NULL DEFAULT '',
            sensitive INTEGER NOT NULL CHECK(sensitive IN (0,1)),
            status TEXT NOT NULL DEFAULT '新案件'
                CHECK(status IN ('新案件','處理中','待員工回覆','已結案')),
            assignee TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            CHECK(kind != 'complaint' OR sensitive = 1)
        );
        CREATE INDEX IF NOT EXISTS cases_employee ON cases(employee_id);
        CREATE INDEX IF NOT EXISTS cases_status ON cases(status);
        CREATE TABLE IF NOT EXISTS case_history (
            id INTEGER PRIMARY KEY,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS webhook_events (
            event_id TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        );
    """)
    db.commit()


def insert_case(data, token):
    """同一 transaction 產生流水號與案件；重送同一 token 不新增。"""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = db.execute("SELECT * FROM cases WHERE submission_token = ?", (token,)).fetchone()
        if existing:
            db.commit()
            return existing
        timestamp = now()
        day = timestamp[:10].replace("-", "")
        counter = db.execute("SELECT next_value FROM case_counters WHERE day = ?", (day,)).fetchone()
        sequence = counter[0] if counter else 1
        if counter:
            db.execute("UPDATE case_counters SET next_value = ? WHERE day = ?", (sequence + 1, day))
        else:
            db.execute("INSERT INTO case_counters VALUES (?, ?)", (day, 2))
        number = "HR-{}-{:03d}".format(day, sequence)
        fields = ["kind", "name", "employee_id", "organization", "category", "title", "description",
                  "event_time", "location", "people", "evidence", "evidence_note", "sensitive"]
        values = [data.get(field, "") for field in fields]
        columns = ["case_number", "submission_token"] + fields + ["created_at", "updated_at"]
        cursor = db.execute("INSERT INTO cases ({}) VALUES ({})".format(
            ",".join(columns), ",".join("?" for _ in columns)), [number, token] + values + [timestamp, timestamp])
        db.execute("INSERT INTO case_history (case_id, created_at, actor, action) VALUES (?, ?, ?, ?)",
                   (cursor.lastrowid, timestamp, "員工", "案件送出 → 新案件"))
        case = db.execute("SELECT * FROM cases WHERE id = ?", (cursor.lastrowid,)).fetchone()
        db.commit()
        return case
    except Exception:
        db.rollback()
        raise
