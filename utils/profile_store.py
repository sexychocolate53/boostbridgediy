# utils/profile_store.py
import os, json, time, sqlite3
from pathlib import Path
import streamlit as st

DB_PATH = Path(os.getenv("PROFILE_DB_PATH", "profiles.db"))

@st.cache_resource
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles(
            email TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    return conn

def get_profile(email: str) -> dict:
    if not email: return {}
    c = _conn().cursor()
    row = c.execute("SELECT data_json FROM profiles WHERE email=?", (email.lower(),)).fetchone()
    if not row: return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}

def save_profile(email: str, data: dict):
    if not email: return
    payload = json.dumps(data, ensure_ascii=False)
    now = int(time.time())
    conn = _conn()
    conn.execute("""
        INSERT INTO profiles(email, data_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            data_json=excluded.data_json,
            updated_at=excluded.updated_at
    """, (email.lower(), payload, now))
    conn.commit()
