# utils/auth.py
# Quota-friendly auth with cached worksheet, single read per minute, and 429 guards.

import os, json, base64, time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import time
from gspread.exceptions import APIError
import bcrypt
from gspread.utils import rowcol_to_a1

# ====== CONFIG ======
USERS_SHEET_ID = "18JDLhCFyMWFTM4JKS3OvvLuJz0Ltkr11D3Y286xOKaQ"
USERS_SHEET_NAME = os.getenv("USERS_SHEET_NAME", "").strip()  # optional: name your tab (e.g. "Users")

PLAN_LIMITS = {
    "individual": {"daily": 1, "monthly": 15},
    "pro": {"daily": 15, "monthly": 200},
}

# ---- SAFE PEPPER LOADING ----
PEPPER = os.getenv("AUTH_PEPPER", "change-me-please")
try:
    if hasattr(st, "secrets") and ("auth_pepper" in st.secrets):
        PEPPER = st.secrets["auth_pepper"]
except Exception:
    pass

# ====== CREDS LOADER ======
SHEETS_SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _with_backoff(fn, *args, **kwargs):
    """Retry on gspread APIError 429 with exponential backoff."""
    delay = 0.5
    for _ in range(6):  # ~0.5 + 1 + 2 + 4 + 8 + 8s
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            msg = str(e).lower()
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 429 or "429" in msg or "quota" in msg:
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            raise
    return fn(*args, **kwargs)

@st.cache_resource
def _get_google_client():
    """One authorized gspread client per process."""
    b64 = os.getenv("GCP_CREDS_B64")
    if b64:
        info = json.loads(base64.b64decode(b64).decode("utf-8"))
        creds = Credentials.from_service_account_info(info, scopes=SHEETS_SCOPE)
        return gspread.authorize(creds)

    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SHEETS_SCOPE
        )
        return gspread.authorize(creds)

    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and os.path.exists(gac):
        creds = Credentials.from_service_account_file(gac, scopes=SHEETS_SCOPE)
        return gspread.authorize(creds)

    proj = Path(__file__).resolve().parents[1]
    p = proj / os.getenv("GOOGLE_CREDS_PATH", "google_creds.json")
    if p.exists():
        creds = Credentials.from_service_account_file(str(p), scopes=SHEETS_SCOPE)
        return gspread.authorize(creds)

    raise RuntimeError("Google credentials not found for Users sheet.")

@st.cache_resource
def _get_users_sheet():
    """Cache the worksheet handle so we don't call open_by_key() repeatedly."""
    client = _get_google_client()
    ss = _with_backoff(client.open_by_key, USERS_SHEET_ID)
    if USERS_SHEET_NAME:
        try:
            return _with_backoff(ss.worksheet, USERS_SHEET_NAME)
        except Exception:
            pass
    return ss.sheet1

# ====== PASSWORDS ======
def hash_password(password: str) -> str:
    salted = (password + PEPPER).encode("utf-8")
    return bcrypt.hashpw(salted, bcrypt.gensalt()).decode("utf-8")

def check_password(password: str, hashed: str) -> bool:
    salted = (password + PEPPER).encode("utf-8")
    try:
        return bcrypt.checkpw(salted, hashed.encode("utf-8"))
    except Exception:
        return False
# ====== PASSWORD RESET (OTP) ======
import random
from datetime import datetime, timedelta, timezone

def _header_map(ws):
    header = ws.row_values(1)
    return {name: i+1 for i, name in enumerate(header)}

def _find_row_by_email(ws, email: str):
    # Prefer an exact match in the Email column if you have one
    hdr = _header_map(ws)
    email_col = hdr.get("email") or hdr.get("Email") or None
    if email_col:
        # Pull the column and search manually to avoid false matches
        col_vals = ws.col_values(email_col)
        for i, v in enumerate(col_vals, start=1):
            if i == 1:  # skip header
                continue
            if (v or "").strip().lower() == email.strip().lower():
                return i
        return None
    # Fallback: first occurrence anywhere
    cell = ws.find(email)
    return cell.row if cell else None

def _now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def _code_expires(minutes=15):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

def _six_digit_code():
    return f"{random.randint(100000, 999999)}"

def request_password_reset(email: str, ttl_minutes: int = 15) -> bool:
    """Generate & store a 6-digit code, email it, return True if user exists."""
    ws = _get_users_sheet()
    row = _find_row_by_email(ws, email)
    if not row:
        return False
    hdr = _header_map(ws)
    code = _six_digit_code()
    expires = _code_expires(ttl_minutes)

    if "reset_code" in hdr:   _with_backoff(ws.update_cell, row, hdr["reset_code"], code)
    if "reset_expires" in hdr:_with_backoff(ws.update_cell, row, hdr["reset_expires"], expires)
    if "reset_attempts" in hdr:_with_backoff(ws.update_cell, row, hdr["reset_attempts"], "0")

    # TODO: replace this stub with your real mailer (SMTP / SendGrid)
    _send_email_stub(
        to_email=email,
        subject="Your BoostBridgeDIY reset code",
        text=f"Your one-time code is: {code}\nIt expires in {ttl_minutes} minutes."
    )
    return True

def verify_reset_code_and_update_password(email: str, code: str, new_password: str) -> tuple[bool, str]:
    """Return (ok, message). On success, writes new bcrypt hash and clears reset fields."""
    if len(new_password) < 8:
        return (False, "Password must be at least 8 characters.")

    ws = _get_users_sheet()
    row = _find_row_by_email(ws, email)
    if not row:
        return (False, "No account found with that email.")

    hdr = _header_map(ws)
    vals = ws.row_values(row)
    rec = {name: (vals[idx-1] if idx-1 < len(vals) else "") for name, idx in hdr.items()}

    saved_code = (rec.get("reset_code") or "").strip()
    expires = (rec.get("reset_expires") or "").strip()

    # Expiry check
    try:
        if not expires or datetime.now(timezone.utc) > datetime.fromisoformat(expires):
            return (False, "Code expired. Please request a new code.")
    except Exception:
        return (False, "Invalid code expiry. Request a new code.")

    # Code check
    if code.strip() != saved_code:
        if "reset_attempts" in hdr:
            try:
                n = int((rec.get("reset_attempts") or "0").strip() or 0) + 1
                _with_backoff(ws.update_cell, row, hdr["reset_attempts"], str(n))
            except Exception:
                pass
        return (False, "Incorrect code.")

    # New bcrypt hash (matches your scheme: bcrypt(password + PEPPER))
    new_hash = hash_password(new_password)

    # Write new password hash
    pw_col = hdr.get("password_hash") or hdr.get("Password Hash") or hdr.get("password")
    if not pw_col:
        return (False, "Password column not found. Make sure 'password_hash' exists.")
    _with_backoff(ws.update_cell, row, pw_col, new_hash)

    # Clear reset fields
    if "reset_code" in hdr:     _with_backoff(ws.update_cell, row, hdr["reset_code"], "")
    if "reset_expires" in hdr:  _with_backoff(ws.update_cell, row, hdr["reset_expires"], "")
    if "reset_attempts" in hdr: _with_backoff(ws.update_cell, row, hdr["reset_attempts"], "0")

    return (True, "Password updated. You can log in now.")

def _send_email_stub(to_email: str, subject: str, text: str):
    """Replace with real email sending (SMTP/SendGrid). Keeping stub so flow works in dev."""
    print(f"[DEV EMAIL] to={to_email}\nSubject: {subject}\n\n{text}\n")


# ====== SHEET READ CACHES ======
import time
from pathlib import Path

@st.cache_data(ttl=180, show_spinner=False)
def _cached_all_users() -> tuple[list[str], list[list[str]]]:
    """
    One spreadsheet read per ~3 minutes (per process) + cross-process throttle
    to avoid 429s. Returns (headers, rows_without_header).
    """
    ws = _get_users_sheet()

    # --- Cross-process anti-stampede throttle ---
    # You can tune via env: USERS_FETCH_MIN_S (default 2.5s)
    min_interval = float(os.getenv("USERS_FETCH_MIN_S", "2.5"))
    gate_file = Path(os.getenv("TMPDIR", "/tmp")) / "bb_users_last_fetch.txt"
    now = time.time()
    try:
        last = float(gate_file.read_text())
    except Exception:
        last = 0.0
    wait = (last + min_interval) - now
    if wait > 0:
        time.sleep(wait)

    # Single read
    values = _with_backoff(ws.get, "A1:Z10000")

    # Stamp the last fetch time (best-effort)
    try:
        gate_file.write_text(str(time.time()))
    except Exception:
        pass

    if not values:
        return [], []
    headers = [h.strip() for h in values[0]]
    rows = values[1:]
    return headers, rows


def _rows_as_dicts_cached() -> List[Dict]:
    headers, rows = _cached_all_users()
    out = []
    for r in rows:
        d = {headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))}
        out.append(d)
    return out

def _clear_user_cache():
    _cached_all_users.clear()

# ====== HELPERS ======
def _find_row_index_by_email(headers: list[str], rows: list[list[str]], email: str) -> Optional[int]:
    email_l = (email or "").strip().lower()
    if not email_l or not headers:
        return None
    try:
        col_idx = next(i for i, h in enumerate(headers) if h.strip().lower() == "email")
    except StopIteration:
        col_idx = 0
    for idx, r in enumerate(rows, start=2):  # rows start at 2 in sheet
        if col_idx < len(r) and (r[col_idx] or "").strip().lower() == email_l:
            return idx
    return None

# ====== USER OPS (quota-safe) ======
def find_user(email: str):
    if not email:
        return None
    email_l = email.strip().lower()
    try:
        headers, raw_rows = _cached_all_users()  # 0 reads if cache warm
    except APIError as e:
        raise  # Let caller handle 429 gracefully
    if not headers:
        return None
    idx = _find_row_index_by_email(headers, raw_rows, email_l)
    if not idx:
        return None
    row_vals = raw_rows[idx - 2]  # zero-based
    d = {headers[i]: (row_vals[i] if i < len(row_vals) else "") for i in range(len(headers))}
    return d

def create_user(email: str, password: str, plan="individual"):
    if not email or not password:
        return False, "Email and password are required."
    if find_user(email):
        return False, "Email already registered."

    ws = _get_users_sheet()
    ph = hash_password(password)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # columns: email | password_hash | plan | active | created_at | daily_count | daily_date | month_count | month_yyyymm
    row = [email.lower(), ph, plan, "TRUE", now, "0", "", "0", ""]
    _with_backoff(ws.append_row, row, value_input_option="USER_ENTERED")
    _clear_user_cache()
    return True, "Account created."

def update_user_counts(email: str, daily_count, daily_date, month_count, month_yyyymm):
    headers, rows = _cached_all_users()
    if not headers:
        return
    row_idx = _find_row_index_by_email(headers, rows, email)
    if not row_idx:
        return
    current = {headers[i]: (rows[row_idx - 2][i] if i < len(rows[row_idx - 2]) else "") for i in range(len(headers))}
    current["daily_count"] = str(daily_count)
    current["daily_date"] = str(daily_date)
    current["month_count"] = str(month_count)
    current["month_yyyymm"] = str(month_yyyymm)
    values = [current.get(h, "") for h in headers]

    ws = _get_users_sheet()
    end_a1 = rowcol_to_a1(row_idx, len(headers))
    _with_backoff(ws.update, f"A{row_idx}:{end_a1}", [values], value_input_option="USER_ENTERED")
    _clear_user_cache()

def refresh_cached_user():
    """Refresh st.session_state.user['record'] from the cached sheet."""
    u = st.session_state.get("user")
    if not u:
        return
    rec = find_user(u["email"])
    if rec:
        u["record"] = rec
        st.session_state.user = u

# --- ADMIN PASSWORD RESET ---
def admin_reset_password(email: str, new_password: str) -> tuple[bool, str]:
    if not email or not new_password:
        return False, "Email and new password are required."
    user = find_user(email)
    if not user:
        return False, "User not found."

    headers, rows = _cached_all_users()
    if not headers:
        return False, "Users sheet unavailable."

    row_idx = _find_row_index_by_email(headers, rows, email)
    if not row_idx:
        return False, "User row not found."

    new_hash = hash_password(new_password)
    current = {headers[i]: (rows[row_idx - 2][i] if i < len(rows[row_idx - 2]) else "") for i in range(len(headers))}
    current["password_hash"] = new_hash
    values = [current.get(h, "") for h in headers]

    ws = _get_users_sheet()
    end_a1 = rowcol_to_a1(row_idx, len(headers))
    _with_backoff(ws.update, f"A{row_idx}:{end_a1}", [values], value_input_option="USER_ENTERED")
    _clear_user_cache()
    return True, "Password reset successfully."

# ====== LIMITS ======
def _rollover_counts(user_dict):
    today = date.today().isoformat()
    yyyymm = f"{date.today().year}{date.today().month:02d}"
    daily_date = user_dict.get("daily_date") or ""
    daily_count = int(user_dict.get("daily_count") or "0")
    month_yyyymm = user_dict.get("month_yyyymm") or ""
    month_count = int(user_dict.get("month_count") or "0")

    if daily_date != today:
        daily_count = 0
        daily_date = today
    if month_yyyymm != yyyymm:
        month_count = 0
        month_yyyymm = yyyymm
    return daily_count, daily_date, month_count, month_yyyymm

def can_generate_letter(user_record: dict):
    plan = (user_record.get("plan") or "individual").lower()
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["individual"])
    daily_count, _, month_count, _ = _rollover_counts(user_record)  # <-- closing parenthesis
    return (daily_count < limits["daily"]) and (month_count < limits["monthly"])


def record_generation(user_record: dict):
    daily_count, daily_date, month_count, month_yyyymm = _rollover_counts(user_record)
    daily_count += 1
    month_count += 1
    email = user_record["email"]
    update_user_counts(email, daily_count, daily_date, month_count, month_yyyymm)
    user_record["daily_count"] = str(daily_count)
    user_record["month_count"] = str(month_count)

def remaining_quota(user_record: dict):
    plan = (user_record.get("plan") or "individual").lower()
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["individual"])
    daily_count, _, month_count, _ = _rollover_counts(user_record)
    return {
        "daily_left": max(0, limits["daily"] - daily_count),
        "monthly_left": max(0, limits["monthly"] - month_count),
        "daily_limit": limits["daily"],
        "monthly_limit": limits["monthly"],
    }

# ====== UI ======
def auth_ui():
    st.sidebar.subheader("🔐 Account")

    # Already logged in?
    if st.session_state.get("user"):
        u = st.session_state["user"]
        st.sidebar.success(f"{u['email']} • plan: {u.get('plan','individual')}")
        rec = u.get("record") or {}
        if rec:
            q = remaining_quota(rec)
            st.sidebar.caption(f"Daily: {q['daily_left']}/{q['daily_limit']} • Monthly: {q['monthly_left']}/{q['monthly_limit']}")
        cols = st.sidebar.columns(2)
        with cols[0]:
            if st.button("Refresh", key="auth_refresh"):
                refresh_cached_user()
                st.rerun()
        with cols[1]:
            if st.button("Logout", key="auth_logout"):
                st.session_state.pop("user", None)
                st.rerun()
        return True

    # Not logged in → Login / Signup tabs (use forms to avoid extra reruns)
    tabs = st.sidebar.tabs(["Login", "Sign up"])

    # ---- Login tab ----
    with tabs[0]:
        with st.form("auth_login_form", clear_on_submit=False):
            li_email = st.text_input("Email", key="auth_login_email")
            li_pw = st.text_input("Password", type="password", key="auth_login_pw")
            login_click = st.form_submit_button("Login", use_container_width=True)

        # init retry counter once
        if "_auth_retry" not in st.session_state:
            st.session_state["_auth_retry"] = 0

        if login_click:
            # in-flight guard
            if st.session_state.get("_auth_login_inflight"):
                st.info("Signing you in…")
                st.stop()
            st.session_state["_auth_login_inflight"] = True

            try:
                user = find_user(li_email)  # single cached read
            except APIError:
                # gentle auto-retry (like your sidebar refresh does)
                attempt = st.session_state["_auth_retry"]
                if attempt < 3:
                    st.info("Syncing your account… one sec.")
                    st.session_state["_auth_retry"] += 1
                    time.sleep(1.2 * (attempt + 1))  # 1.2s, 2.4s, 3.6s
                    st.session_state["_auth_login_inflight"] = False
                    st.rerun()
                else:
                    st.session_state["_auth_retry"] = 0
                    st.session_state["_auth_login_inflight"] = False
                    st.error("We’re syncing with Google. Please try again in a few seconds.")
                    st.stop()

            if not user or (user.get("active","").upper() != "TRUE"):
                st.session_state["_auth_login_inflight"] = False
                st.error("Invalid credentials or inactive account.")
                st.stop()

            if not check_password(li_pw, user.get("password_hash","")):
                st.session_state["_auth_login_inflight"] = False
                st.error("Invalid credentials.")
                st.stop()

            # success
            st.session_state.user = {
                "email": user["email"],
                "plan": user.get("plan","individual"),
                "record": user,
            }
            st.session_state["_auth_retry"] = 0
            st.session_state["_auth_login_inflight"] = False

            # pre-warm caches (best-effort)
            try:
                _ = _cached_all_users()
                from utils.jobs import _cached_jobs_table
                _ = _cached_jobs_table()
            except Exception:
                pass

            st.success("Login successful.")
            st.rerun()
        

    # ---- Sign up tab ----
    with tabs[1]:
        with st.form("auth_signup_form", clear_on_submit=False):
            su_email = st.text_input("Email", key="auth_signup_email")
            su_pw = st.text_input("Password", type="password", key="auth_signup_pw")
            su_pw2 = st.text_input("Confirm Password", type="password", key="auth_signup_pw2")
            signup_click = st.form_submit_button("Create Account", use_container_width=True)

        if signup_click:
            if su_pw != su_pw2 or len(su_pw) < 8:
                st.error("Passwords must match and be at least 8 chars.")
                st.stop()

            try:
                ok, msg = create_user(su_email, su_pw, plan="individual")
            except APIError:
                # brief retry like login
                if st.session_state.get("_signup_retry", 0) < 3:
                    st.info("Creating your account… one sec.")
                    st.session_state["_signup_retry"] = st.session_state.get("_signup_retry", 0) + 1
                    time.sleep(1.2 * st.session_state["_signup_retry"])
                    st.rerun()
                else:
                    st.session_state["_signup_retry"] = 0
                    st.error("We’re syncing with Google. Please try again in a few seconds.")
                    st.stop()

            if ok:
                # Build a minimal local record to avoid another read right now.
                new_record = {
                    "email": su_email.lower(),
                    "plan": "individual",
                    "active": "TRUE",
                    "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "daily_count": "0",
                    "daily_date": "",
                    "month_count": "0",
                    "month_yyyymm": "",
                }
                st.session_state.user = {
                    "email": new_record["email"],
                    "plan": new_record["plan"],
                    "record": new_record,
                }
                st.session_state["_signup_retry"] = 0

                # pre-warm caches (best-effort)
                try:
                    _ = _cached_all_users()
                    from utils.jobs import _cached_jobs_table
                    _ = _cached_jobs_table()
                except Exception:
                    pass

                st.success("Account created and logged in.")
                st.rerun()
            else:
                st.error(msg)

