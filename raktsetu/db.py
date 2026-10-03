import sqlite3, os
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS banks(id INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL, lon REAL, open_24x7 INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS hospitals(id INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL, lon REAL, license_no TEXT UNIQUE, verified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS donors(id INTEGER PRIMARY KEY, name TEXT NOT NULL, blood_group TEXT NOT NULL, lat REAL, lon REAL, last_donation TEXT, verified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS units(
  id INTEGER PRIMARY KEY, bank_id INTEGER NOT NULL REFERENCES banks(id),
  blood_group TEXT NOT NULL, component TEXT NOT NULL CHECK(component IN ('RBC','PLT')),
  collected_on TEXT NOT NULL, expires_on TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','reserved','issued','expired')));
CREATE INDEX IF NOT EXISTS idx_units_lookup ON units(status, component, blood_group, expires_on);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT);
"""

def connect(path=None):
    path = path or os.environ.get("RAKTSETU_DB", "raktsetu.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn

def log(conn, actor, action, detail=""):
    conn.execute("INSERT INTO audit_log(ts,actor,action,detail) VALUES(?,?,?,?)",
                 (datetime.now().isoformat(timespec="seconds"), actor, action, detail))
