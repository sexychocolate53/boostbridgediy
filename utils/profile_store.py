# utils/profile_store.py
import os, json, sqlite3
import streamlit as st

# On Streamlit Cloud, /mount/data is the writable directory.
# You can override with env var PROFILE_DB_DIR if you want.
DB_DIR  = os.environ.get("PROFILE_DB_DIR", "/mount/data")
DB_PATH = os.path.join(DB_DIR, "profiles.db")

DDL = """
CREATE TABLE IF NOT EXISTS profiles (
  email      TEXT PRIMARY KEY,
  data       TEXT NOT NULL,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def _ensure_db():
    os.makedirs(DB_DIR, exist_ok=True)
    # Use a fresh connection per call; allow cross-thread use
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        conn.execute(DDL)
        conn.commit()

def _load(email: str) -> dict:
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cur = conn.execute(
            "SELECT data FROM profiles WHERE lower(email)=lower(?)",
            (email or "",),
        )
        row = cur.fetchone()
    return json.loads(row[0]) if row and row[0] else {}

def _save(email: str, data: dict) -> None:
    payload = json.dumps(data or {}, ensure_ascii=False)
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        conn.execute(
            """
            INSERT INTO profiles(email, data, updated_at)
            VALUES(?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE
            SET data=excluded.data, updated_at=CURRENT_TIMESTAMP
            """,
            (email or "", payload),
        )
        conn.commit()

def get_profile(email: str) -> dict:
    """Return saved profile or {}. Falls back to in-memory cache if DB is unavailable."""
    if not email:
        return {}
    try:
        _ensure_db()
        return _load(email)
    except Exception:
        cache = st.session_state.setdefault("_profile_cache", {})
        return cache.get((email or "").lower(), {})

def save_profile(email: str, profile: dict) -> None:
    """Persist profile. Falls back to in-memory cache if DB is unavailable."""
    if not email:
        return
    try:
        _ensure_db()
        _save(email, profile or {})
    except Exception:
        cache = st.session_state.setdefault("_profile_cache", {})
        cache[(email or "").lower()] = profile or {}
