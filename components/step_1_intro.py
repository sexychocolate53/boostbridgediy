# components/step_1_intro.py
import os, json, base64
from pathlib import Path
from datetime import datetime
import socket
import streamlit as st
from google.oauth2.service_account import Credentials
import streamlit as st
from utils.auth import find_user, _cached_all_users, _get_users_sheet, _with_backoff

def _sheet_consent(email: str) -> bool:
    """Read consent from Users sheet (column named 'consent' if present). Falls back to False."""
    rec = find_user(email) or {}
    v = str(rec.get("consent", "")).strip().lower()
    return v in {"1", "true", "yes", "y"}

def _set_sheet_consent(email: str, value: bool = True) -> None:
    """Write consent to Users sheet if a 'consent' column exists; otherwise cache locally."""
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
    for idx, r in enumerate(rows, start=2):
        if col_email < len(r) and (r[col_email] or "").strip().lower() == email_l:
            row_idx = idx
            break
    if row_idx is None:
        st.session_state["consent_ok"] = bool(value)
        return

    # write only if a 'consent' column exists
    try:
        col_consent = next(i for i, h in enumerate(headers) if h.strip().lower() == "consent")
    except StopIteration:
        st.session_state["consent_ok"] = bool(value)
        return

    ws = _get_users_sheet()
    _with_backoff(ws.update_cell, row_idx, col_consent + 1, "TRUE" if value else "FALSE")
    st.session_state["consent_ok"] = bool(value)


# ✅ Centralized consent helpers (BoostBridge sheet, no duplicates)
#from utils.access_gate import has_consent, record_consent

# ---------- Config ----------
SHEETS_SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# Legacy/optional disclaimer log (you already had this)
DISCLAIMER_SHEET_ID = "1V8bqD1MMyza7x1XvPDbO0Un6mqFqC5ds0Ga_DT4q0ac"

def k(name: str) -> str:
    return f"s1_{name}"

# Robust credential loader: secrets -> base64 env -> path env -> local file
def get_google_creds():
    # 1) Streamlit secrets
    if "gcp_service_account" in st.secrets:
        return Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SHEETS_SCOPE
        )
    # 2) Base64 env var
    if os.getenv("GCP_CREDS_B64"):
        info = json.loads(base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8"))
        return Credentials.from_service_account_info(info, scopes=SHEETS_SCOPE)
    # 3) Path env var
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=SHEETS_SCOPE
        )
    # 4) Local file (resolve from project root even when called from /components)
    project_root = Path(__file__).resolve().parents[1]
    creds_path = project_root / os.getenv("GOOGLE_CREDS_PATH", "google_creds.json")
    if creds_path.exists():
        return Credentials.from_service_account_file(str(creds_path), scopes=SHEETS_SCOPE)
    # None found: return None (we'll handle gracefully)
    return None

def log_disclaimer_if_possible(full_name: str, email: str):
    """Try to log acceptance to the legacy DISCLAIMER_SHEET_ID; fail softly if not configured."""
    try:
        creds = get_google_creds()
        if not creds or not DISCLAIMER_SHEET_ID:
            return False

        import gspread  # import here so missing package doesn't break the whole page
        client = gspread.authorize(creds)
        sheet = client.open_by_key(DISCLAIMER_SHEET_ID).sheet1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ip_address = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip_address = "unknown"
        sheet.append_row([timestamp, full_name, email, ip_address, "Agreed"])
        return True
    except Exception:
        # Don’t block the user if logging fails
        return False

def _current_user_email() -> str:
    return (
        (st.session_state.get("user") or {}).get("email")
        or st.session_state.get("user_email")
        or st.session_state.get("email")
        or ""
    )

def _current_user_name() -> str:
    ui = st.session_state.get("user_info") or {}
    return ui.get("full_name", "")

def render():
    st.title("📄 AI Credit Dispute Letter Generator")

    st.markdown(
        """
Welcome to your personal AI-powered letter builder.

This tool generates **law-backed, FCRA-compliant** dispute letters customized to your exact situation — no copy-paste templates.

---

""",
    )

    # Single disclaimer box
    st.markdown(
        """
<div style='background-color:#fff3cd; padding:15px; border-radius:8px; border:1px solid #ffeeba;'>
<strong>⚠️ Important:</strong> This tool is for <strong>personal use only</strong>.<br/>
Using it to generate letters for others (friends, clients, etc.) is strictly prohibited and will result in <strong>immediate cancellation of your subscription without refund</strong>.
</div>
""",
        unsafe_allow_html=True,
    )

    # --- New: centralized consent (no duplicates; uses BoostBridge sheet) ---
    email = _current_user_email().strip().lower()
    full_name = _current_user_name()

    if not email:
        st.error("We couldn't detect your account email. Please log in again.")
        return

    already = has_consent(email)

    if already:
        st.success("✅ Consent on file. Thank you!")
        if st.button("Continue", key=k("continue_existing")):
            st.session_state.step = 2
            st.rerun()
        return

    # Not consented yet — show a single checkbox and log once
    agreed = st.checkbox(
        "I understand and agree to use this system for personal purposes only.",
        key=k("agree_cb"),
    )

    # Optional name/email inputs preserved (for legacy disclaimer log only)
    with st.expander("Add your name & email (optional, for legacy consent log)"):
        full_name_override = st.text_input("Full name", key=k("full_name"))
        email_override = st.text_input("Email", key=k("email"))

    if not agreed:
        st.info("Check the box to enable the Continue button.")

    if st.button("Continue", key=k("continue_btn"), disabled=not agreed):
        # 1) Central consent (BoostBridge sheet) — prevents duplicates automatically
        try:
            record_consent(email=email, name=(full_name or full_name_override or ""))
        except Exception:
            pass  # soft fail

        # 2) Legacy optional logging to DISCLAIMER_SHEET_ID (kept from your original)
        _legacy_name = full_name_override or full_name or "Unknown"
        _legacy_email = email_override or email or "Unknown"
        try:
            log_disclaimer_if_possible(_legacy_name, _legacy_email)
        except Exception:
            pass  # soft fail

        st.session_state.step = 2
        st.rerun()


