# utils/jobs.py
import os, json, time, base64
from pathlib import Path

import streamlit as st
import gspread
from gspread.exceptions import APIError
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Read the Jobs sheet id from Secrets first (then env as fallback)
JOBS_SHEET_ID = st.secrets.get("JOBS_SHEET_ID") or os.getenv("JOBS_SHEET_ID")

# keep this for local dev fallback only
GA_CRED_PATH  = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# include Drive scope too so gspread can open the file
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
LOCAL_TZ = ZoneInfo("America/New_York")


# ---- small caches to reduce read spam (helps avoid 429) ----
_WS_MEMO = {"ws": None, "ts": 0}
_LIST_CACHE = {"key": "", "rows": [], "ts": 0}  # ~20s cache for list_jobs_for_email

# Extra columns we manage for follow-ups / SMS scheduling
FOLLOWUP_COLS = [
    "phone_cached",       # normalized phone copied from payload
    "sms_opt_in",         # True/False copied from payload
    "first_sms_due_at",   # ISO date string for first reminder (e.g., created + 10 days)
    "last_sms_at",        # last time an SMS was sent
    "sms_status",         # e.g., "pending", "sent", "failed"
]

# Your main headers (keep as-is to match your sheet)
HEADERS = [
    "letter_id", "status", "email", "bureau", "dispute_type", "round_name",
    "payload_json", "letter_text", "qa_notes", "created_at", "updated_at"
]

def now_local_str():
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")

def _with_backoff(fn, *args, **kwargs):
    """Retry Sheets calls on quota/429; raise last error if all retries fail."""
    delay = 1.5
    last_exc = None
    for _ in range(5):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            last_exc = e
            msg = str(e).lower()
            if "429" in msg or "quota" in msg:
                time.sleep(delay)
                delay = min(delay * 2, 12)
                continue
            raise
    # if we got here, retries exhausted
    raise last_exc if last_exc else RuntimeError("Unknown Sheets error")

def _client():
    """
    Authorize gspread using (in order):
      1) st.secrets['gcp_service_account']  (Streamlit Cloud recommended)
      2) GCP_CREDS_B64 (base64 JSON in env)
      3) GOOGLE_APPLICATION_CREDENTIALS file path (local/dev)
      4) ./google_creds.json (local/dev)
    """
    creds = None

    # 1) Streamlit Secrets
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPE
        )

    # 2) Base64 env var
    elif os.getenv("GCP_CREDS_B64"):
        info = json.loads(base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8"))
        creds = Credentials.from_service_account_info(info, scopes=SCOPE)

    # 3) File path (local/dev)
    elif GA_CRED_PATH and os.path.exists(GA_CRED_PATH):
        creds = Credentials.from_service_account_file(GA_CRED_PATH, scopes=SCOPE)

    # 4) Local repo file (local/dev)
    else:
        project_root = Path(__file__).resolve().parents[1]
        guess = project_root / os.getenv("GOOGLE_CREDS_PATH", "google_creds.json")
        if guess.exists():
            creds = Credentials.from_service_account_file(str(guess), scopes=SCOPE)

    if creds is None:
        raise FileNotFoundError(
            "Google credentials not found. Set st.secrets['gcp_service_account'] "
            "or GCP_CREDS_B64 / GOOGLE_APPLICATION_CREDENTIALS / google_creds.json."
        )
    if not JOBS_SHEET_ID:
        raise FileNotFoundError(
            "JOBS_SHEET_ID is not set. Add it to Streamlit Secrets (or env)."
        )

    return gspread.authorize(creds)

def _open_jobs_ws():
    """
    Open (or create) the 'Jobs' worksheet and ensure headers exist.
    Uses a 5-min memo so we don’t call open_by_key() every time.
    """
    if _WS_MEMO["ws"] and (time.time() - _WS_MEMO["ts"] < 300):
        return _WS_MEMO["ws"]

    gc = _client()
    sh = _with_backoff(gc.open_by_key, JOBS_SHEET_ID)
    try:
        ws = _with_backoff(sh.worksheet, "Jobs")
    except gspread.WorksheetNotFound:
        # try to use the first sheet if it already has our headers
        ws = sh.sheet1
        first_row = _with_backoff(ws.row_values, 1) or []
        if [h.lower() for h in first_row[:len(HEADERS)]] != [h.lower() for h in HEADERS]:
            # doesn’t look like our jobs sheet → create a new tab named "Jobs"
            ws = _with_backoff(sh.add_worksheet, title="Jobs", rows=1000, cols=len(HEADERS))
            _with_backoff(ws.update, f"A1:{rowcol_to_a1(1, len(HEADERS))}",
                          [HEADERS], value_input_option="USER_ENTERED")

    # Ensure our base headers are present (case-insensitive)
    first_row = _with_backoff(ws.row_values, 1) or []
    if [h.lower() for h in first_row[:len(HEADERS)]] != [h.lower() for h in HEADERS]:
        new_cols = max(ws.col_count, len(HEADERS))
        _with_backoff(ws.resize, rows=max(ws.row_count, 1), cols=new_cols)
        _with_backoff(ws.update, f"A1:{rowcol_to_a1(1, len(HEADERS))}",
                      [HEADERS], value_input_option="USER_ENTERED")

    _WS_MEMO["ws"] = ws
    _WS_MEMO["ts"] = time.time()
    return ws


    # Ensure our base headers are present (case-insensitive) without shrinking columns
    first_row = _with_backoff(ws.row_values, 1) or []
    if [h.lower() for h in first_row[:len(HEADERS)]] != [h.lower() for h in HEADERS]:
        new_cols = max(ws.col_count, len(HEADERS))
        _with_backoff(ws.resize, rows=max(ws.row_count, 1), cols=new_cols)
        _with_backoff(ws.update, f"A1:{rowcol_to_a1(1, len(HEADERS))}", [HEADERS], value_input_option="USER_ENTERED")

    _WS_MEMO["ws"] = ws
    _WS_MEMO["ts"] = time.time()
    return ws

def _ensure_min_cols(ws, min_cols: int):
    """Grow grid columns if needed so we can safely write headers past current col_count."""
    if ws.col_count < min_cols:
        _with_backoff(ws.add_cols, min_cols - ws.col_count)

def _ensure_followup_columns(ws):
    """
    Guarantee FOLLOWUP_COLS exist on header row; grow grid first if needed,
    then write missing headers in one range update.
    """
    headers = _with_backoff(ws.row_values, 1) or []
    missing = [h for h in FOLLOWUP_COLS if h not in headers]
    if not missing:
        return

    target_cols = len(headers) + len(missing)
    _ensure_min_cols(ws, target_cols)

    start_col = len(headers) + 1
    end_col   = start_col + len(missing) - 1
    a1_range  = f"{rowcol_to_a1(1, start_col)}:{rowcol_to_a1(1, end_col)}"
    _with_backoff(ws.update, a1_range, [missing], value_input_option="USER_ENTERED")

def _pick_header(headers: list[str], options: list[str]) -> str | None:
    """Return the first header name that exists (case-insensitive), or None."""
    lowers = {h.lower(): h for h in headers}
    for opt in options:
        if opt.lower() in lowers:
            return lowers[opt.lower()]
    return None

def add_job_row(letter_id: str, email: str, bureau: str, dispute_type: str,
                round_name: str, payload: dict):
    """
    Append ONE row including follow-up columns — no extra reads after append.
    Keeps API traffic low to avoid 429s.
    """
    ws = _open_jobs_ws()

    # ensure follow-up headers exist (single update to header row)
    _ensure_followup_columns(ws)

    # snapshot headers and build index map
    headers = _with_backoff(ws.row_values, 1) or []
    colmap  = {h: i for i, h in enumerate(headers)}  # 0-based

    # choose whichever timestamp headers your sheet actually has
    created_hdr = _pick_header(headers, ["created_at_local", "created_at"])
    updated_hdr = _pick_header(headers, ["updated_at_local", "updated_at"])

    created_ts = now_local_str()

    # derive follow-up values from payload
    user   = (payload or {}).get("user", {}) or {}
    phone  = (user.get("phone") or "").strip()
    sms_ok = bool(user.get("sms_opt_in", False))
    try:
        first_due = (datetime.strptime(created_ts, "%Y-%m-%d %H:%M:%S") + timedelta(days=10)).strftime("%Y-%m-%d")
    except Exception:
        first_due = ""

    # prepare full row sized to header count
    row = [""] * len(headers)

    def setv(hname: str, value):
        idx = colmap.get(hname)
        if idx is not None:
            row[idx] = value

    # core cols
    setv("letter_id", letter_id)
    setv("status", "queued")
    setv("email", email)
    setv("bureau", bureau)
    setv("dispute_type", dispute_type)
    # support either "round" or "round_name"
    setv("round", round_name)
    setv("round_name", round_name)
    setv("payload_json", json.dumps(payload, ensure_ascii=False))
    setv("letter_text", "")
    setv("qa_notes", "")
    if created_hdr: setv(created_hdr, created_ts)
    if updated_hdr: setv(updated_hdr, created_ts)

    # follow-up cols (in same single append)
    setv("phone_cached", phone)
    setv("sms_opt_in", "TRUE" if sms_ok else "FALSE")
    setv("first_sms_due_at", first_due if (sms_ok and phone) else "")
    setv("last_sms_at", "")
    setv("sms_status", "pending" if (sms_ok and phone) else "")

    # one API call
    _with_backoff(ws.append_row, row, value_input_option="USER_ENTERED")

def get_job_by_id(letter_id: str) -> dict | None:
    ws = _open_jobs_ws()
    headers = _with_backoff(ws.row_values, 1) or []
    rows = _with_backoff(ws.get_all_values) or []
    for i in range(1, len(rows)):  # skip header
        r = rows[i]
        if r and r[0] == letter_id:
            return {h: (r[idx] if idx < len(r) else "") for idx, h in enumerate(headers)}
    return None

def get_jobs_for_email(email: str) -> list[dict]:
    """Convenience for a 'My Jobs' page (no caching)."""
    ws = _open_jobs_ws()
    headers = _with_backoff(ws.row_values, 1) or []
    records = (_with_backoff(ws.get_all_values) or [])[1:]
    out = []
    low = (email or "").lower()
    for row in records:
        rec = {h: (row[idx] if idx < len(row) else "") for idx, h in enumerate(headers)}
        if (rec.get("email") or "").lower() == low:
            out.append(rec)
    return out

def list_jobs_for_email(email: str, limit: int = 25) -> list[dict]:
    """Return recent jobs for an email (most recent last), cached ~20s to avoid bursts."""
    key = f"{(email or '').lower()}::{limit}"
    if _LIST_CACHE["key"] == key and (time.time() - _LIST_CACHE["ts"] < 20):
        return _LIST_CACHE["rows"]

    ws = _open_jobs_ws()
    headers = _with_backoff(ws.row_values, 1) or []
    rows = _with_backoff(ws.get_all_values) or []
    out = []
    low = (email or "").lower()
    for i in range(1, len(rows)):
        r = rows[i]
        rec = {h: (r[idx] if idx < len(r) else "") for idx, h in enumerate(headers)}
        if (rec.get("email") or "").lower() == low:
            out.append(rec)
    out = out[-limit:]

    _LIST_CACHE["key"] = key
    _LIST_CACHE["rows"] = out
    _LIST_CACHE["ts"] = time.time()
    return out

def update_job(letter_id: str, **fields) -> bool:
    """
    Update a job by letter_id. Example:
      update_job("john-transunion-20250813-101234",
                 status="approved", letter_text="...", qa_notes="{}")
    """
    ws = _open_jobs_ws()
    headers = _with_backoff(ws.row_values, 1) or []
    rows = _with_backoff(ws.get_all_values) or []

    colmap = {h: i for i, h in enumerate(headers)}
    # prefer whichever updated_at header you actually have
    updated_hdr = _pick_header(headers, ["updated_at_local", "updated_at"])

    for i in range(1, len(rows)):  # row index in sheet is i+1
        row = rows[i]
        if row and row[0] == letter_id:
            curr = {h: (row[colmap[h]] if colmap[h] < len(row) else "") for h in headers}
            curr.update(fields)
            if updated_hdr:
                curr[updated_hdr] = now_local_str()

            out = [curr.get(h, "") for h in headers]
            start_row = i + 1
            _with_backoff(ws.update, f"A{start_row}:{rowcol_to_a1(start_row, len(headers))}", [out], value_input_option="USER_ENTERED")
            return True
    return False

def update_job_fields(letter_id: str, **fields):
    """Update arbitrary columns by name for a single job row."""
    ws = _open_jobs_ws()
    headers = _with_backoff(ws.row_values, 1) or []
    colmap = {h: idx + 1 for idx, h in enumerate(headers)}
    rows = _with_backoff(ws.get_all_values) or []

    # prefer updating updated_at_local if present
    if "updated_at_local" in colmap and "updated_at_local" not in fields:
        fields["updated_at_local"] = now_local_str()
    elif "updated_at" in colmap and "updated_at" not in fields:
        fields["updated_at"] = now_local_str()

    target_row = None
    for i in range(1, len(rows)):
        if rows[i] and rows[i][0] == letter_id:
            target_row = i + 1  # 1-based
            break
    if not target_row:
        raise ValueError(f"Job not found: {letter_id}")

    updates = []
    for k, v in fields.items():
        c = colmap.get(k)
        if not c:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        a1 = rowcol_to_a1(target_row, c)
        updates.append({"range": a1, "values": [[v]]})
    if updates:
        _with_backoff(ws.batch_update, updates, value_input_option="USER_ENTERED")

def find_job_in_list(jobs: list[dict], letter_id: str) -> dict | None:
    """Return the job dict with this letter_id from a pre-fetched list; None if not found."""
    lid = (letter_id or "").strip()
    if not lid:
        return None
    for j in reversed(jobs or []):
        if (j.get("letter_id") or "").strip() == lid:
            return j
    return None

def requeue_job(letter_id: str, payload: dict | None = None):
    """
    Set status back to 'queued', optionally replace payload_json,
    and clear qa_notes so the worker starts fresh.
    """
    fields = {"status": "queued", "qa_notes": ""}
    if payload is not None:
        fields["payload_json"] = json.dumps(payload, ensure_ascii=False)
    update_job_fields(letter_id, **fields)

