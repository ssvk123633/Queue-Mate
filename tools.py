from datetime import datetime, timedelta
import sqlite3
import hashlib
import secrets

AVG_SERVICE_MIN = 6
DB_PATH = "queue.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tokens (
            token_no INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            counter TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            created_at TEXT NOT NULL,
            phone TEXT,
            place TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS visitors (
            visitor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            age INTEGER,
            place TEXT,
            counter TEXT,
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS otp_requests (
            phone TEXT PRIMARY KEY,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.commit()
    conn.close()


def get_queue_status(token_no: int):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT counter FROM tokens WHERE token_no = ?", (token_no,)
    ).fetchone()
    counter = row[0] if row else None

    if counter:
        ahead = conn.execute(
            "SELECT COUNT(*) FROM tokens WHERE status='waiting' AND counter=? AND token_no<?",
            (counter, token_no),
        ).fetchone()[0]
    else:
        ahead = conn.execute(
            "SELECT COUNT(*) FROM tokens WHERE status='waiting' AND token_no<?",
            (token_no,),
        ).fetchone()[0]
    conn.close()
    return {"people_ahead": ahead, "est_wait_min": ahead * AVG_SERVICE_MIN}


def book_token(name: str, counter: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO tokens(name, counter, status, created_at) VALUES (?,?,?,?)",
        (name, counter, "waiting", datetime.now().isoformat()),
    )
    conn.commit()
    token_no = cur.lastrowid
    conn.close()
    return {"token_no": token_no, "counter": counter}


def create_otp(phone: str):
    init_db()
    otp = f"{secrets.randbelow(900000) + 100000}"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    expires_at = (datetime.now() + timedelta(minutes=5)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO otp_requests(phone, otp_hash, expires_at, attempts) VALUES (?,?,?,0) "
        "ON CONFLICT(phone) DO UPDATE SET otp_hash=excluded.otp_hash, expires_at=excluded.expires_at, attempts=0",
        (phone, otp_hash, expires_at),
    )
    conn.commit()
    conn.close()
    return otp


def verify_otp(phone: str, otp: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT otp_hash, expires_at, attempts FROM otp_requests WHERE phone=?", (phone,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    otp_hash, expires_at, attempts = row
    if datetime.now().isoformat() > expires_at or attempts >= 5:
        conn.close()
        return False
    if hashlib.sha256(otp.encode()).hexdigest() != otp_hash:
        conn.execute("UPDATE otp_requests SET attempts=? WHERE phone=?", (attempts + 1, phone))
        conn.commit()
        conn.close()
        return False
    conn.execute("DELETE FROM otp_requests WHERE phone=?", (phone,))
    conn.execute("UPDATE visitors SET verified=1 WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    return True


def register_visitor(name: str, phone: str, age: int, place: str, counter: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO visitors(name, phone, age, place, counter, verified, created_at) "
        "VALUES (?,?,?,?,?,0,?) "
        "ON CONFLICT(phone) DO UPDATE SET name=excluded.name, age=excluded.age, place=excluded.place, "
        "counter=excluded.counter, verified=0, created_at=excluded.created_at",
        (name, phone, age, place, counter, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"phone": phone, "name": name, "place": place, "counter": counter}


def complete_token(token_no: int):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("UPDATE tokens SET status='completed' WHERE token_no=? AND status='waiting'", (token_no,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return {"token_no": token_no, "status": "completed" if changed else "not_found"}


init_db()