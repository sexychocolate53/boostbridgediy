# app.py  — BoostBridgeDIY • AI Letters (clean single-file version)

import os, time, json
from textwrap import dedent
from datetime import datetime
from typing import List, Tuple, Optional

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


# ---------- Streamlit page config ----------
st.set_page_config(
    page_title="BoostBridgeDIY • AI Letters",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Top Nav (single definition) ----------
def render_top_nav(
    contact_email: str,
    brand: str = "BoostBridgeDIY",
    links: list[tuple[str, str]] | None = None,
    cta_text: str | None = "Join Beta",
    cta_url: str | None = "#",
):
    if links is None:
        links = [("Docs", "#"), ("Privacy", "#"), ("Terms", "#")]

    bg   = "#0f172a"   # slate-900
    fg   = "#e2e8f0"   # slate-200
    acc  = "#22c55e"   # green-500
    link = "#93c5fd"   # blue-300

    html = dedent(f"""
    <style>
      .block-container {{ padding-top: 1.2rem; }}
      .bb-nav {{ position: sticky; top: 0; z-index: 9999; background: {bg}; color: {fg};
                 border-radius: 12px; padding: 10px 16px; margin-bottom: 1rem;
                 box-shadow: 0 10px 20px rgba(2,6,23,.25); }}
      .bb-row {{ display:flex; align-items:center; gap:14px; justify-content:space-between; flex-wrap:wrap; }}
      .bb-brand {{ font-weight:700; letter-spacing:.3px; font-size:1.05rem; }}
      .bb-links a {{ color:{link}; text-decoration:none; margin:0 8px; font-size:.95rem; }}
      .bb-links a:hover {{ text-decoration:underline; }}
      .bb-cta a {{ background:{acc}; color:#052e16; border-radius:10px; padding:8px 12px;
                   font-weight:700; text-decoration:none; display:inline-block; }}
      .bb-contact a {{ color:{fg}; text-decoration:none; opacity:.9; }}
      .bb-contact a:hover {{ text-decoration:underline; opacity:1; }}
      @media (max-width: 680px) {{
        .bb-links {{ width:100%; order:3; margin-top:6px; }}
        .bb-cta {{ order:2; }}
      }}
    </style>

    <div class="bb-nav">
      <div class="bb-row">
        <div class="bb-brand">🧠 {brand} <span style="opacity:.65;">• AI Letters</span></div>
        <div class="bb-cta">
          {("<a href='" + cta_url + "' target='_blank'>" + cta_text + "</a>") if cta_text and cta_url else ""}
        </div>
        <div class="bb-links">
          {" ".join([f"<a href='{u}' target='_blank'>{t}</a>" for t,u in links])}
          <span class="bb-contact" style="margin-left:10px; opacity:.75;">|
            <a href="mailto:{contact_email}">{contact_email}</a></span>
        </div>
      </div>
    </div>
    """)

    st.markdown(html, unsafe_allow_html=True)

# ---------- Footer (define once, use once) ----------
def render_footer(contact_email: str = "boostbridgediy@gmail.com"):
    st.markdown(
        f"""
        <hr style="margin-top:28px; margin-bottom:12px; border: 0; border-top: 1px solid #eef2f7;" />
        <div style="color:#6b7280; font-size:.85rem;">
          © {datetime.now().year} BoostBridgeDIY •
          <a href="mailto:{contact_email}" style="text-decoration:none;">Contact</a> •
          Personal-use tool, not legal advice.
        </div>
        """,
        unsafe_allow_html=True,
    )

# Render the nav immediately (safe: functions are already defined)
render_top_nav(contact_email="stacy@boostbridgediy.com", brand="BoostBridgeDIY")

# ---------- Load env & initialize third-party clients ----------
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- Jobs sheet helper (writes only; no reads here) ----------
import gspread
from google.oauth2.service_account import Credentials
from zoneinfo import ZoneInfo
LOCAL_TZ = ZoneInfo("America/New_York")
JOBS_SHEET_ID = os.getenv("JOBS_SHEET_ID")

def now_local_str() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")

def open_jobs_sheet():
    # Reuse service account creds
    if os.path.exists("service_account.json"):
        creds = Credentials.from_service_account_file(
            "service_account.json",
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        gc = gspread.authorize(creds)
    else:
        gc = gspread.service_account()
    return gc.open_by_key(JOBS_SHEET_ID).sheet1

def add_job_row(letter_id: str, email: str, bureau: str, dispute_type: str, round_name: str, intake_payload: dict):
    ws = open_jobs_sheet()
    row = [
        letter_id,
        "queued",
        email,
        bureau,
        dispute_type,
        round_name,
        json.dumps(intake_payload, ensure_ascii=False),  # initial payload_json
        "",   # letter_text
        "",   # qa_notes
        now_local_str(),
        now_local_str()
    ]
    # Write is OK; reads are what trigger per-minute 429s
    ws.append_row(row, value_input_option="USER_ENTERED")

# ---------- Imports that rely on env after load_dotenv ----------
from gspread.exceptions import APIError
from utils.auth import auth_ui, find_user, remaining_quota, refresh_cached_user
# Optional tracker
try:
    from utils.credit_tracker import init_tracker_if_needed, render_sidebar_badge
    _HAS_TRACKER = True
except Exception:
    _HAS_TRACKER = False

# ---------- Global quota helpers (pre-warm + call/step guards) ----------
def prewarm_caches_once():
    """Best-effort warm of caches to avoid cold-start 429s."""
    if st.session_state.get("_bb_prewarmed"):
        return
    try:
        # Users cache
        from utils.auth import _cached_all_users
        _ = _cached_all_users()
    except Exception:
        pass
    try:
        # Jobs cache
        from utils.jobs import _cached_jobs_table
        _ = _cached_jobs_table()
    except Exception:
        pass
    st.session_state["_bb_prewarmed"] = True

def quota_retry_call(key: str, fn, *args, **kwargs):
    """
    Run a Sheets-backed function with bounded auto-retry & backoff.
    Falls back to a 'Retry now' button instead of telling users to refresh.
    """
    n = st.session_state.get(key, 0)
    from gspread.exceptions import APIError
    try:
        result = fn(*args, **kwargs)
        st.session_state[key] = 0
        return result
    except APIError as e:
        msg = str(e).lower()
        if "429" in msg or "quota" in msg:
            if n < 6:
                st.session_state[key] = n + 1
                st.info("Syncing… one sec.")
                import time as _t
                _t.sleep(0.8 * (n + 1))
                st.rerun()
            else:
                st.session_state[key] = 0
                c1, c2 = st.columns([1, 6])
                with c1:
                    if st.button("Retry now", key=f"retry_call_{int(datetime.now().timestamp())}"):
                        st.rerun()
                with c2:
                    st.info("Still syncing. Click **Retry now** — your inputs are safe.")
                st.stop()
        raise


# ---------- Global quota helpers (pre-warm + call/step guards) ----------
def safe_render(step_fn):
    """
    Render a step with a global APIError 429 guard.
    Auto-retries with backoff. If it still can't, shows a 'Retry' button that
    runs st.rerun() (does NOT clear session_state / typed fields).
    """
    key = "_global_retry"
    n = st.session_state.get(key, 0)
    from gspread.exceptions import APIError
    try:
        step_fn()
        st.session_state[key] = 0
    except APIError as e:
        msg = str(e).lower()
        if "429" in msg or "quota" in msg:
            # Try up to 6 times with gentle backoff
            if n < 6:
                st.session_state[key] = n + 1
                st.info("Syncing… one sec.")
                import time as _t
                _t.sleep(0.8 * (n + 1))  # 0.8, 1.6, 2.4, 3.2, 4.0, 4.8s
                st.rerun()
            else:
                # Stop auto-looping. Provide a *local* retry button that won't clear inputs.
                st.session_state[key] = 0
                c1, c2 = st.columns([1, 6])
                with c1:
                    if st.button("Retry now", key=f"retry_{int(datetime.now().timestamp())}"):
                        st.rerun()
                with c2:
                    st.info("Still syncing. Click **Retry now** above — no data will be lost.")
                st.stop()
        else:
            raise


# ---------- Public landing (when not logged in) ----------
def render_public_landing():
    st.markdown(
        """
        <style>
          .block-container {padding-top: 3rem; padding-bottom: 3rem;}
          .hero-wrap {background: linear-gradient(180deg, #f8fbff 0%, #ffffff 60%);
            border-radius: 18px; padding: 36px 28px; border: 1px solid #eef2f7;}
          .hero-title {font-size: 2.2rem; line-height: 1.15; margin: 0 0 8px 0;}
          .hero-sub {color:#4b5563; font-size:1.05rem; margin-bottom: 14px;}
          .pill {display:inline-block; padding:6px 10px; border-radius:999px;
                 background:#eef6ff; color:#2563eb; font-weight:600; font-size:.78rem;}
          .card {background:#fff; border:1px solid #eef2f7; border-radius:16px; padding:18px; height:100%;}
          .card h4 {margin:0 0 6px 0;}
          .muted {color:#6b7280;}
          .tiny {font-size:.85rem;}
          .footer {color:#6b7280; font-size:.8rem; margin-top: 24px;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown("<span class='pill'>BoostBridgeDIY</span>", unsafe_allow_html=True)
        st.markdown(
            "<div class='hero-wrap'>"
            "<div class='hero-title'>AI Credit Dispute Letter Generator</div>"
            "<div class='hero-sub'>Law-backed, consumer-friendly letters with clear steps "
            "(Personal Info → R1 → R2 → R3). No templates — tailored language based on your inputs.</div>"
            "<div class='tiny muted'>Use the <b>Login / Sign up</b> panel on the left to get started.</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.write("")  # spacer

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                "<div class='card'><h4>📄 Real Letters</h4>"
                "<div class='tiny muted'>Writes body-only text that avoids boilerplate and adds your header/signature automatically.</div></div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                "<div class='card'><h4>⚖️ FCRA-aware</h4>"
                "<div class='tiny muted'>Plain-English requests: reinvestigation, MOV details, correct-or-delete, and updated report.</div></div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                "<div class='card'><h4>🧭 Clear Rounds</h4>"
                "<div class='tiny muted'>Personal Info cleanup → Round 1 → Round 2 (MOV/Factual) → Round 3 (the other).</div></div>",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                "<div class='card'><h4>📝 History</h4>"
                "<div class='tiny muted'>Your letters are saved locally and logged to your access sheet for usage tracking.</div></div>",
                unsafe_allow_html=True,
            )

        st.write("")  # spacer

        st.subheader("How it works", anchor="how-it-works")
        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown("<div class='card'><h4>1) Pick items</h4>"
                        "<div class='tiny muted'>Choose a category and add up to 5 accounts (or items) with quick facts.</div></div>",
                        unsafe_allow_html=True)
        with s2:
            st.markdown("<div class='card'><h4>2) Add basics</h4>"
                        "<div class='tiny muted'>Provide your name/address/DOB/last-4 so the letter can be personalized.</div></div>",
                        unsafe_allow_html=True)
        with s3:
            st.markdown("<div class='card'><h4>3) Generate</h4>"
                        "<div class='tiny muted'>Download TXT/PDF immediately. We log only minimal metadata for your usage count.</div></div>",
                        unsafe_allow_html=True)

        st.markdown(
            "<div class='footer'>This tool is for personal use. It provides general guidance and letters, "
            "but it is not legal advice.</div>",
            unsafe_allow_html=True,
        )

# ---------- Auth gate ----------
logged_in = auth_ui()
if not logged_in:
    render_public_landing()
    render_footer("stacy@boostbridgediy.com")
    st.stop()

# Fresh session bootstrap: ensure we start at Step 1 on first load after login
if "wizard_initialized" not in st.session_state:
    for k in [
        "step",
        "dispute_types", "dispute_details", "account_items",
        "selected_bureau", "round_name", "dispute_round", "round_strategy",
        "law_selection",
        "user_info", "user_full_name", "user_address", "user_city", "user_state",
        "user_zip_code", "user_ssn_last4", "user_dob",
        "generated_letter", "current_letter_id",
        "help_chat",
    ]:
        st.session_state.pop(k, None)
    st.session_state.step = 1
    st.session_state.wizard_initialized = True
    # Pre-warm caches once for this session
    prewarm_caches_once()
    st.rerun()   # silently rerun into Step 1

# ---------- Access control ----------
email = (
    (st.session_state.get("user") or {}).get("email")
    or st.session_state.get("user_email")
    or st.session_state.get("email")
)
if not email:
    st.error("No email found for the current session.")
    st.stop()

# --- Access & quotas (Users sheet only) ---
from utils.auth import find_user, remaining_quota

user_rec = (st.session_state.get("user") or {}).get("record") or find_user(email) or {}
rq = remaining_quota(user_rec)  # {'daily_left','monthly_left','daily_limit','monthly_limit'}
plan = (user_rec.get("plan") or "individual").lower()

# Gentle banner if they’re out of daily credits (don’t block the app here;
# Step 8 blocks generation when credits are exhausted)
if rq["daily_left"] <= 0 and plan != "pro":
    st.info(
        "You’ve hit today’s limit for your plan. "
        "You can still review steps; generation will be blocked until reset."
    )

# --- Sidebar: Letter Credits ---
def _render_letter_credits_sidebar(q: dict):
    st.sidebar.subheader("💌 Letter Credits")
    st.sidebar.caption(
        f"Daily: {int(q['daily_left'])}/{int(q['daily_limit'])} • "
        f"Monthly: {int(q['monthly_left'])}/{int(q['monthly_limit'])}"
    )
    # Big monthly remaining number
    st.sidebar.markdown(
        f"""
        <div style="font-size:28px;font-weight:800;line-height:1;margin:2px 0 6px 0;">
            {int(q.get('monthly_left', 0))}
        </div>
        <div style="color:#6b7280;margin:-2px 0 8px 0;">remaining this month</div>
        """,
        unsafe_allow_html=True,
    )
    # Progress bar shows monthly remaining fraction
    denom = max(1, int(q["monthly_limit"]))
    pct = float(q["monthly_left"]) / float(denom)
    st.sidebar.progress(pct)

_render_letter_credits_sidebar(rq)

# Optional tracker bootstrap (if you use it)
try:
    if _HAS_TRACKER and not st.session_state.get("tracker_initialized"):
        init_tracker_if_needed(mode=plan, starting_credits=int(rq["monthly_left"]))
        st.session_state.tracker_initialized = True
except Exception:
    pass

# --- Admin check (no 'meta' anywhere) ---
admin_str = ""
try:
    admin_str = str(st.secrets.get("ADMIN_EMAILS", ""))  # comma- or semicolon-separated
except Exception:
    admin_str = ""
allowed_admins = {e.strip().lower() for e in admin_str.replace(";", ",").split(",") if e.strip()}

user_is_admin = (
    (email or "").lower() in allowed_admins
    or (user_rec.get("role", "").strip().lower() == "admin")
)

# ------ Admin check ------
def _is_truthy(v):
    return str(v).strip().lower() in {"true", "1", "yes", "y"}

# Option A: mark admins in the Users sheet with role=admin or is_admin=TRUE
# Option B: or set an environment variable ADMIN_EMAILS="alice@x.com,bob@y.com"
ADMIN_EMAILS = {s.strip().lower() for s in os.getenv("ADMIN_EMAILS", "").split(",") if s.strip()}

IS_ADMIN = (
    (meta.get("role", "").strip().lower() == "admin")
    or _is_truthy(meta.get("is_admin", ""))
    or (email.lower() in ADMIN_EMAILS)
)

# keep in session so pages can also check it if needed
st.session_state["_is_admin"] = IS_ADMIN


# ---------- Sidebar quick nav ----------
if st.sidebar.button("🎓 Tips & Education"):
    st.session_state.step = 98
    st.rerun()

if st.sidebar.button("📜 Dispute History"):
    st.session_state.step = 99
    st.rerun()

# replace your Dashboard button
if st.session_state.get("_is_admin") and st.sidebar.button("📊 Dashboard"):
    st.session_state.step = 100
    st.rerun()


st.sidebar.markdown("---")

# ---------- Sidebar helper (mini assistant) ----------
def sidebar_helper():
    st.sidebar.subheader("💬 Quick Help")
    if "help_chat" not in st.session_state:
        st.session_state.help_chat = []

    for msg in st.session_state.help_chat[-8:]:
        role = "You" if msg["role"] == "user" else "Assistant"
        st.sidebar.markdown(f"**{role}:** {msg['content']}")

    user_q = st.sidebar.text_area("Ask about this step:", height=80, key="help_q")

    c1, c2 = st.sidebar.columns(2)
    if c1.button("Ask", key="help_ask"):
        if user_q.strip():
            st.session_state.help_chat.append({"role": "user", "content": user_q.strip()})
            system_prompt = (
                "You are an in-app helper for a credit-dispute letter generator. "
                "Be concise, step-specific, and avoid legal advice. "
                "If the user asks for legal advice, say you cannot provide it. "
                "Explain fields, flow, and general law meanings in plain language."
            )
            try:
                resp = client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "system", "content": system_prompt}, *st.session_state.help_chat],
                    temperature=0.4,
                    max_tokens=300,
                )
                answer = (resp.choices[0].message.content or "").strip()
            except Exception as e:
                answer = f"Sorry—something went wrong: {e}"
            st.session_state.help_chat.append({"role": "assistant", "content": answer})
            st.rerun()

    if c2.button("Clear", key="help_clear"):
        st.session_state.help_chat = []
        st.rerun()

sidebar_helper()

# ---------- Steps router ----------
from components import (
    step_1_intro,
    step_2_dispute_type,
    step_3_bureau_select,
    step_4_select_dispute_type,
    step_4_5_dispute_details,
    step_5_round_select,
    step_6_law_selection,
    step_7_user_info,
    step_8_generate_letter,
    page_history,
    page_education,
    page_dashboard,
)

# Normalize step (handle ints, strings, 4.5)
raw_step = st.session_state.get("step", 1)
try:
    step_num = float(raw_step)
except Exception:
    step_num = 1.0

st.sidebar.title("Navigation")
st.sidebar.markdown(f"Current Step: **{raw_step}**")

if "selected_bureau" in st.session_state:
    st.info(f"📌 Bureau Selected: **{st.session_state.selected_bureau}**")

# Route with quota-safe rendering
if step_num == 1:
    safe_render(step_1_intro.render)
elif step_num == 2:
    safe_render(step_2_dispute_type.render)
elif step_num == 3:
    safe_render(step_3_bureau_select.render)
elif step_num == 4:
    safe_render(step_4_select_dispute_type.render)
elif step_num == 4.5:
    safe_render(step_4_5_dispute_details.render)
elif step_num == 5:
    safe_render(step_5_round_select.render)
elif step_num == 6:
    safe_render(step_6_law_selection.render)
elif step_num == 7:
    safe_render(step_7_user_info.render)
elif step_num == 7.5:
    from components import step_7_5_review_confirm
    safe_render(step_7_5_review_confirm.render)
elif step_num == 8:
    safe_render(step_8_generate_letter.render)
elif step_num == 98:
    safe_render(page_education.render)
elif step_num == 99:
    safe_render(page_history.render)
elif step_num == 100:
    if not st.session_state.get("_is_admin"):
        st.warning("That page is only available to admins.")
        st.session_state.step = 1
        st.rerun()
    else:
        safe_render(page_dashboard.render)

else:
    st.warning("Unknown step. Resetting to Step 1.")
    st.session_state.step = 1
    st.rerun()

# ---------- Footer (always last) ----------
render_footer("stacy@boostbridgediy.com")




