# components/step_1_intro.py
import os, json, base64
from pathlib import Path
from datetime import datetime
import socket
import streamlit as st
from google.oauth2.service_account import Credentials

# ---------- Config ----------
SHEETS_SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
DISCLAIMER_SHEET_ID = "1V8bqD1MMyza7x1XvPDbO0Un6mqFqC5ds0Ga_DT4q0ac"  # <- your sheet

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
    """Try to log acceptance to Google Sheets; fail softly if creds/sheet not configured."""
    try:
        creds = get_google_creds()
        if not creds:
            return False  # no creds configured; skip logging silently

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

    # Acknowledge
    agreed = st.checkbox(
        "I understand and agree to use this system for personal purposes only.",
        key=k("agree_cb"),
    )

    # Optional name/email (don’t rely on session here)
    with st.expander("Add your name & email (optional, helps us log your consent)"):
        full_name = st.text_input("Full name", key=k("full_name"))
        email = st.text_input("Email", key=k("email"))

    # Continue button
    disabled = not agreed
    if st.button("Continue", key=k("continue_btn"), disabled=disabled):
        # Try to log acceptance (soft-fail)
        log_disclaimer_if_possible(full_name or "Unknown", email or "Unknown")
        st.session_state.step = 2
        st.rerun()

    # Helpful tip if they haven't checked the box
    if not agreed:
        st.info("Check the box to enable the Continue button.")
