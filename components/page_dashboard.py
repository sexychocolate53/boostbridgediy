# components/page_dashboard.py
import os, json
from datetime import datetime, timedelta
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Optional extra columns that may or may not exist yet
OPTIONAL_COLS = [
    "phone_cached", "sms_opt_in", "first_sms_due_at", "last_sms_at", "sms_status"
]

@st.cache_data(ttl=20, show_spinner=False)
def _open_ws_and_read(spreadsheet_id: str):
    """Open the first worksheet and return (headers, rows_as_dicts). Cached for 20s."""
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        creds = Credentials.from_service_account_file(cred_path, scopes=scope)
        gc = gspread.authorize(creds)
    else:
        gc = gspread.service_account()

    ss = gc.open_by_key(spreadsheet_id)
    try:
        ws = ss.sheet1  # first tab
    except Exception:
        # fallback to first worksheet if sheet1 alias not present
        ws = ss.get_worksheet(0)

    vals = ws.get_all_values()
    headers = vals[0] if vals else []
    rows = []
    for r in vals[1:]:
        rows.append({headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))})
    return headers, rows

def _parse_date(dt_str: str):
    """Best-effort parse for 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'."""
    dt_str = (dt_str or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except Exception:
            pass
    return None

def render():
    st.header("📊 Dashboard")

    ssid = os.getenv("JOBS_SHEET_ID")
    if not ssid:
        st.error("JOBS_SHEET_ID not configured in .env")
        return

    try:
        headers, jobs = _open_ws_and_read(ssid)
    except Exception as e:
        st.error(f"Could not read Jobs sheet: {e}")
        return

    # --- Top metrics
    total = len(jobs)
    approved = sum(1 for j in jobs if (j.get("status","").strip().lower() == "approved"))
    needs_fix = sum(1 for j in jobs if (j.get("status","").strip().lower() == "needs_fix"))
    queued = sum(1 for j in jobs if (j.get("status","").strip().lower() == "queued"))

    c1, c2, c3 = st.columns(3)
    c1.metric("Total letters", total)
    c2.metric("Approved", approved)
    c3.metric("Needs Fix", needs_fix)

    # Optional: SMS-ready metric if columns exist
    have_sms_cols = all(c in headers for c in ["phone_cached", "sms_opt_in"])
    if have_sms_cols:
        sms_ready = sum(
            1 for j in jobs
            if (j.get("sms_opt_in","").strip().upper() in {"TRUE","1","YES"})
            and (j.get("phone_cached","").strip() != "")
        )
        st.caption(f"📱 SMS-ready rows: **{sms_ready}**")

    # --- By bureau
    st.subheader("By Bureau")
    by_bureau = {}
    for j in jobs:
        b = (j.get("bureau","") or "—").strip()
        by_bureau[b] = by_bureau.get(b, 0) + 1
    # simple display
    st.write({k: v for k, v in sorted(by_bureau.items(), key=lambda x: -x[1])})

    # --- Last 7 days created
    st.subheader("Last 7 days")
    cutoff = datetime.now() - timedelta(days=7)
    recent = 0
    for j in jobs:
        d = _parse_date(j.get("created_at_local","")[:19])  # trim to seconds if longer
        if d and d >= cutoff:
            recent += 1
    st.write(f"{recent} created in the last 7 days.")

    # --- Status breakdown (quick glance)
    st.subheader("Status breakdown")
    by_status = {}
    for j in jobs:
        s = (j.get("status","") or "—").strip().lower()
        by_status[s] = by_status.get(s, 0) + 1
    st.write(by_status)

    # --- Latest jobs (20)
    st.subheader("Recent (latest 20)")
    latest = sorted(
        jobs,
        key=lambda x: x.get("updated_at_local",""),
        reverse=True
    )[:20]

    # Hide huge payloads in the table view for readability
    def _trim(row: dict):
        r = row.copy()
        if "payload_json" in r and len(r["payload_json"]) > 140:
            r["payload_json"] = r["payload_json"][:140] + "…"
        if "qa_notes" in r and len(r["qa_notes"]) > 140:
            r["qa_notes"] = r["qa_notes"][:140] + "…"
        return r

    st.dataframe([_trim(r) for r in latest], use_container_width=True)
