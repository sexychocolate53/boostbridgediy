# utils/access_gate.py
import os, json
from typing import Tuple, Optional, Dict
from datetime import datetime, date

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError

# Worksheets in the BoostBridgeDIY Access spreadsheet
USERS_SHEET   = "UsersAccess"
LOG_SHEET     = "LetterLog"
CONSENT_SHEET = "Consent"

# Credit limits by plan (adjust to your tiers)
PLAN_LIMITS = {
    "starter": 15,       # example: Starter = 1/day
    "individual": 15,    # your current UI default
    "pro": -1,           # -1 = unlimited
}

# ---------- Google client (cached) ----------
@st.cache_resource
def _gc_from_env():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path or not os.path.exists(cred_path):
        raise FileNotFoundError(
            "Google credentials file not found. Set GOOGLE_APPLICATION_CREDENTIALS in your .env"
        )
    with open(cred_path, "r") as f:
        service_account_info = json.load(f)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]  # sheets only; open_by_key
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)

def _open_sheet(gc, wks_name: str):
    """
    Open the worksheet by name, creating it if missing.
    If a concurrent create happened (Google returns 400 'already exists'),
    recover by opening the existing tab. Headers are only written on first create.
    """
    sheet_id = os.getenv("BOOSTBRIDGE_ACCESS_SHEET_ID")
    if not sheet_id:
        raise EnvironmentError(
            "Missing BOOSTBRIDGE_ACCESS_SHEET_ID in your .env "
            "(from https://docs.google.com/spreadsheets/d/<THIS_ID>/edit)"
        )
    sh = gc.open_by_key(sheet_id)

    try:
        return sh.worksheet(wks_name)
    except WorksheetNotFound:
        # Create with appropriate size + headers
        try:
            if wks_name == USERS_SHEET:
                ws = sh.add_worksheet(title=USERS_SHEET, rows=2000, cols=12)
                ws.update(
                    "A1:I1",
                    [[
                        "email","plan","active","created_at",
                        "daily_count","daily_date","month_count","month_yyyymm","renewal_date"
                    ]],
                    value_input_option="USER_ENTERED"
                )
                return ws
            elif wks_name == LOG_SHEET:
                ws = sh.add_worksheet(title=LOG_SHEET, rows=2000, cols=10)
                ws.update(
                    "A1:F1",
                    [["ts","email","bureau","dispute_type","account_ref","letter_id"]],
                    value_input_option="USER_ENTERED"
                )
                return ws
            elif wks_name == CONSENT_SHEET:
                ws = sh.add_worksheet(title=CONSENT_SHEET, rows=2000, cols=6)
                ws.update(
                    "A1:C1",
                    [["email","name","ts"]],
                    value_input_option="USER_ENTERED"
                )
                return ws
            else:
                # Generic sheet create if ever called with a different name
                ws = sh.add_worksheet(title=wks_name, rows=1000, cols=10)
                return ws
        except APIError as e:
            # If another process created it milliseconds earlier, just open it
            if "already exists" in str(e).lower():
                return sh.worksheet(wks_name)
            raise

# ---------- Cached lookups to reduce API calls ----------
def _email_col_index(ws) -> int:
    headers = ws.row_values(1)
    for i, h in enumerate(headers, start=1):
        if str(h).strip().lower() == "email":
            return i
    return 1

@st.cache_data(ttl=60)
def _cached_user_row(email: str) -> Dict | None:
    """Return dict for user row or None (cached)."""
    if not email:
        return None
    target = str(email).strip().lower()
    gc = _gc_from_env()
    ws = _open_sheet(gc, USERS_SHEET)
    headers = ws.row_values(1)
    col_idx = _email_col_index(ws)
    vals = ws.col_values(col_idx)
    # start at row 2 (skip header)
    for i in range(2, len(vals) + 1):
        if str(vals[i-1]).strip().lower() == target:
            row_vals = ws.row_values(i)
            if len(row_vals) < len(headers):
                row_vals += [""] * (len(headers) - len(row_vals))
            return dict(zip(headers, row_vals)) | {"_row": i}
    return None

@st.cache_data(ttl=300)
def _cached_has_consent(email: str) -> bool:
    if not email:
        return False
    target = str(email).strip().lower()
    gc = _gc_from_env()
    ws = _open_sheet(gc, CONSENT_SHEET)
    headers = ws.row_values(1)
    col = next((i+1 for i,h in enumerate(headers) if str(h).strip().lower()=="email"), 1)
    vals = ws.col_values(col)
    return any(str(v).strip().lower() == target for v in vals[1:])

# ---------- Public helpers ----------
def get_or_create_user(email: str) -> Tuple[Dict, int]:
    """
    Returns (user_dict, row_index).
    Creates a new row with defaults if not found.
    Uses cached read path to avoid rate limits.
    """
    cached = _cached_user_row(email)
    today = date.today().isoformat()
    yyyymm = today[:7].replace("-", "")

    if cached:
        row_idx = cached.pop("_row")
        user = dict(cached)
        # roll daily/month if needed
        changed = False
        if user.get("daily_date") != today:
            user["daily_count"] = "0"; user["daily_date"] = today; changed = True
        if user.get("month_yyyymm") != yyyymm:
            user["month_count"] = "0"; user["month_yyyymm"] = yyyymm; changed = True
        if changed:
            gc = _gc_from_env()
            ws = _open_sheet(gc, USERS_SHEET)
            headers = ws.row_values(1)
            _write_user(ws, user, headers, row_idx)
            _cached_user_row.clear()  # invalidate cache
        return user, row_idx

    # not found -> create
    gc = _gc_from_env()
    ws = _open_sheet(gc, USERS_SHEET)
    user = {
        "email": email,
        "plan": "starter",
        "active": "TRUE",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "daily_count": "0",
        "daily_date": today,
        "month_count": "0",
        "month_yyyymm": yyyymm,
        "renewal_date": "",
    }
    ws.append_row(list(user.values()), value_input_option="USER_ENTERED")
    # find row index we just wrote
    idx = _find_user_row(ws, email) or len(ws.col_values(1))
    _cached_user_row.clear()
    return user, idx

def _find_user_row(ws, email: str) -> Optional[int]:
    if not email:
        return None
    email = str(email).strip().lower()
    col_idx = _email_col_index(ws)
    vals = ws.col_values(col_idx)
    for i in range(2, len(vals) + 1):
        if str(vals[i-1]).strip().lower() == email:
            return i
    return None

def _write_user(ws, user: Dict, headers: list, row_idx: int):
    row_values = [user.get(h, "") for h in headers]
    ws.update(
        f"A{row_idx}:{gspread.utils.rowcol_to_a1(row_idx, len(headers))}",
        [row_values],
        value_input_option="USER_ENTERED"
    )

def get_user_meta(email: str) -> dict:
    """Return the UsersAccess row as a dict (creates if missing)."""
    user, _ = get_or_create_user(email)
    return user

def get_remaining_credits_today(email: str) -> int:
    """Compute remaining credits from UsersAccess daily_count + plan limit."""
    user = get_user_meta(email)
    plan = (user.get("plan") or "individual").lower()
    limit = PLAN_LIMITS.get(plan, 15)
    if limit < 0:
        return -1
    used = int(user.get("daily_count") or 0)
    return max(0, limit - used)

def guard_access(email: str, starter_daily_limit: int = 3) -> Dict:
    """Raises if inactive or over limit. Returns user dict if ok."""
    user, _ = get_or_create_user(email)
    is_active = str(user.get("active","")).strip().upper() in ("TRUE","1","YES")
    if not is_active:
        raise PermissionError("Subscription inactive")
    plan = (user.get("plan") or "").lower()
    if plan == "starter" and int(user.get("daily_count") or 0) >= starter_daily_limit:
        raise RuntimeError("Starter daily limit reached")
    return user

def increment_counters_and_log(email: str, bureau: str, dispute_type: str,
                               account_ref: str, letter_id: str):
    """Increment daily/month counters and append a log row. Clears cache after write."""
    gc = _gc_from_env()
    # increment on Users sheet
    ws_u = _open_sheet(gc, USERS_SHEET)
    row_idx = _find_user_row(ws_u, email)
    if row_idx:
        headers = ws_u.row_values(1)
        vals = ws_u.row_values(row_idx)
        if len(vals) < len(headers):
            vals += [""] * (len(headers) - len(vals))
        user = dict(zip(headers, vals))
        user["daily_count"] = str(int(user.get("daily_count") or 0) + 1)
        user["month_count"] = str(int(user.get("month_count") or 0) + 1)
        _write_user(ws_u, user, headers, row_idx)

    # append to LetterLog
    ws_l = _open_sheet(gc, LOG_SHEET)
    ts = datetime.utcnow().isoformat()
    ws_l.append_row([ts, email, bureau, dispute_type, account_ref, letter_id], value_input_option="USER_ENTERED")

    # invalidate caches
    _cached_user_row.clear()

# ---------- Consent helpers (no duplicate rows) ----------
def has_consent(email: str) -> bool:
    if not email:
        return False
    key = f"consent::{email}"
    if key in st.session_state:
        return st.session_state[key]
    ok = _cached_has_consent(email)
    st.session_state[key] = ok
    return ok

def record_consent(email: str, name: str = ""):
    if not email:
        return
    if has_consent(email):
        return
    gc = _gc_from_env()
    ws = _open_sheet(gc, CONSENT_SHEET)
    ws.append_row([email, name or "", datetime.utcnow().isoformat()], value_input_option="USER_ENTERED")
    _cached_has_consent.clear()
    st.session_state[f"consent::{email}"] = True
