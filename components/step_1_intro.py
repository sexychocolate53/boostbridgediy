# components/step_1_intro.py
import os, json, base64, socket
from pathlib import Path
from datetime import datetime
import streamlit as st

# We use ONLY utils.auth for sheet access (no access_gate here)
from utils.auth import find_user, _cached_all_users, _get_users_sheet, _with_backoff

# (Optional) legacy disclaimer logging — safe to leave; it silently no-ops if not configured
try:
    from google.oauth2.service_account import Credentials
except Exception:
    Credentials = None  # keep import optional so we never crash

SHEETS_SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
DISCLAIMER_SHEET_ID = os.getenv("DISCLAIMER_SHEET_ID", "").strip()  # optional

def k(name: str) -> str:
    return f"s1_{name}"

# ---------- Consent helpers stored in Users sheet (column "consent") ----------
def _sheet_consent(email: str) -> bool:
    rec = find_user(email) or {}
    v = str(rec.get("consent", "")).strip().lower()
    return v in {"1", "true", "yes", "y"}

def _set_sheet_consent(email: str, value: bool = True) -> None:
    headers, rows = _cached_all_users()
    if not headers or not email:
        st.session_state["consent_ok"] = bool(value)
        return

    email_l = email.strip().lower()
    try:
        col_email = next(i for i, h in enumerate(headers) if h.strip().lower() == "email")
    except StopIteration:
        col_email = 0

    row_idx = None
    for idx, r in enumerate(rows, start=2):  # +2 because header is row 1
        if col_email < len(r) and (r[col_email] or "").strip().lower() == email_l:
            row_idx = idx
            break
    if row_idx is None:
        st.session_state["consent_ok"] = bool(value)
        return

    # only write if a "consent" column exists
    try:
        col_consent = next(i for i, h in enumerate(headers) if h.strip().lower() == "consent")
    except StopIteration:
        st.session_state["consent_ok"] = bool(value)
        return

    ws = _get_users_sheet()
    _with_backoff(ws.update_cell, row_idx, col_consent + 1, "TRUE" if value else "FALSE")
    st.session_state["consent_ok"] = bool(value)

# ---------- Optional, safe legacy logging ----------
def _get_google_creds():
    if not Credentials:
        return None
    # 1) Streamlit secrets
    try:
        if "gcp_service_account" in st.secrets:
            return Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=SHEETS_SCOPE
            )
    except Exception:
        pass
    # 2) Base64 env var
    try:
        if os.getenv("GCP_CREDS_B64"):
            info = json.loads(base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8"))
            return Credentials.from_service_account_info(info, scopes=SHEETS_SCOPE)
    except Exception:
        pass
    # 3) Path env var
    try:
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return Credentials.from_service_account_file(
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=SHEETS_SCOPE
            )
    except Exception:
        pass
    # 4) Local file
    try:
        project_root = Path(__file__).resolve().parents[1]
        creds_path = project_root / os.getenv("GOOGLE_CREDS_PATH", "google_creds.json")
        if creds_path.exists():
            return Credentials.from_service_account_file(str(creds_path), scopes=SHEETS_SCOPE)
    except Exception:
        pass
    return None

def _legacy_log_disclaimer(full_name: str, email: str):
    """Best effort; never blocks if not configured."""
    try:
        if not DISCLAIMER_SHEET_ID:
            return
        creds = _get_google_creds()
        if not creds:
            return
        import gspread
        client = gspread.authorize(creds)
        sheet = client.open_by_key(DISCLAIMER_SHEET_ID).sheet1
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "unknown"
        sheet.append_row([ts, full_name, email, ip, "Agreed"])
    except Exception:
        pass  # always soft-fail

# ---------- Current user helpers ----------
def _current_user_email() -> str:
    return (
        (st.session_state.get("user") or {}).get("email")
        or st.session_state.get("user_email")
        or st.session_state.get("email")
        or ""
    ).strip().lower()

def _current_user_name() -> str:
    ui = st.session_state.get("user_info") or {}
    return (ui.get("full_name") or "").strip()

# ---------- Page ----------
def render():
    st.title("📄 AI Credit Dispute Letter Generator")
    st.markdown(
        """
Welcome to your personal AI-powered letter builder.

This tool generates **law-backed, FCRA-compliant** dispute letters customized to your exact situation — no copy-paste templates.

---
"""
    )

    st.markdown(
        """
<div style='background-color:#fff3cd; padding:15px; border-radius:8px; border:1px solid #ffeeba;'>
<strong>⚠️ Important:</strong> This tool is for <strong>personal use only</strong>.<br/>
Using it to generate letters for others (friends, clients, etc.) is strictly prohibited and will result in <strong>immediate cancellation of your subscription without refund</strong>.
</div>
""",
        unsafe_allow_html=True,
    )

    email = _current_user_email()
    full_name = _current_user_name()
    if not email:
        st.error("We couldn't detect your account email. Please log in again.")
        return

    # Read consent (no access_gate calls)
    already = st.session_state.get("consent_ok")
    if already is None:
        try:
            already = _sheet_consent(email)
        except Exception:
            already = False
        st.session_state["consent_ok"] = bool(already)

    if already:
        st.success("✅ Consent on file. Thank you!")
        if st.button("Continue", key=k("continue_existing")):
            st.session_state.step = 2
            st.rerun()
        return

    agreed = st.checkbox(
        "I understand and agree to use this system for personal purposes only.",
        key=k("agree_cb"),
    )

    with st.expander("Add your name & email (optional, for legacy consent log)"):
        full_name_override = st.text_input("Full name", key=k("full_name"))
        email_override = st.text_input("Email", key=k("email"))

    if not agreed:
        st.info("Check the box to enable the Continue button.")

    if st.button("Continue", key=k("continue_btn"), disabled=not agreed):
        # 1) Persist consent in Users sheet (our single source of truth)
        _set_sheet_consent(email, True)

        # 2) Optional legacy log
        _legacy_log_disclaimer(
            full_name_override or full_name or "Unknown",
            email_override or email or "Unknown",
        )

        st.session_state.step = 2
        st.rerun()
