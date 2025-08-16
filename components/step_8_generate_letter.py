# components/step_8_generate_letter.py
import os, io, re, json
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from fpdf import FPDF
import time
from gspread.exceptions import APIError

# jobs utils (de-duped import)
from utils.jobs import list_jobs_for_email, find_job_in_list, requeue_job

from utils.prompt_builder import build_prompt
from utils.history import save_letter_files, log_dispute
from utils.access_gate import (
    get_user_meta,
    get_remaining_credits_today,
    increment_counters_and_log,
)
from utils.credit_tracker import (
    lock_or_validate_user,
    cannot_spend_reason,
    spend_one_credit,
)

# credit + user record helpers (Users sheet counters)
from utils.auth import (
    find_user,
    can_generate_letter,
    record_generation,     # deduct Users sheet credit after success
    remaining_quota,
    refresh_cached_user,   # refresh st.session_state.user['record'] so sidebar updates
)

def _k(name: str) -> str:
    return f"s8_{name}"

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

REPLACEMENTS = {
    "\u2022": "-", "\u2013": "-", "\u2014": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\xa0": " ",
}
def _ascii_sanitize(s: str) -> str:
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")

def _strip_salutation_and_signature(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^(?:\s*(?:dear\b[^\n]*,|to whom[^\n]*,?|hello[^\n]*,?)\s*\n)+','',t,flags=re.IGNORECASE).lstrip()
    t = re.sub(r'\n\s*(?:dear\b[^\n]*,|to whom[^\n]*,?|hello[^\n]*,?)\s*\n','\n',t,flags=re.IGNORECASE)
    t = re.split(r'\n\s*(?:sincerely|regards|respectfully)\b.*', t, flags=re.IGNORECASE)[0].rstrip()
    return re.sub(r'\n{3,}', '\n\n', t)

BUREAU_ADDRESSES = {
    "Equifax": "Equifax Information Services LLC\nP.O. Box 740256\nAtlanta, GA 30374",
    "Experian": "Experian\nP.O. Box 4500\nAllen, TX 75013",
    "TransUnion": "TransUnion Consumer Solutions\nP.O. Box 2000\nChester, PA 19016-2000",
}

def render():
    st.header("Step 8: Generate Your Letter")

    # show sidebar toast if we just updated credits on last run
    if st.session_state.pop("__credits_updated__", False):
        st.sidebar.success("Credits updated.")

    needed = ["dispute_types", "dispute_details", "selected_bureau", "user_info"]
    if not any(st.session_state.get(k) for k in needed):
        st.session_state.step = 1
        st.rerun()
        return

    # ---------- JOB PANEL (single read; utils caches & backoffs) ----------
    email_for_jobs = (
        (st.session_state.get("user") or {}).get("email")
        or st.session_state.get("user_email")
        or st.session_state.get("email")
        or ""
    )

    # before you read jobs, initialize a retry counter once
    if "jobs_retry" not in st.session_state:
        st.session_state["jobs_retry"] = 0

    try:
        jobs = list_jobs_for_email(email_for_jobs, limit=25)
        # success → reset counter
        st.session_state["jobs_retry"] = 0
    except APIError:
        attempt = st.session_state["jobs_retry"]
        if attempt < 3:  # 3 gentle retries max
            st.info("Syncing your recent jobs… one sec.")
            st.session_state["jobs_retry"] += 1
            time.sleep(1.2 * (attempt + 1))  # backoff: 1.2s, 2.4s, 3.6s
            st.rerun()
        else:
            st.session_state["jobs_retry"] = 0
            st.info("Still syncing. Tap Refresh or try again shortly.")
            jobs = []

    if jobs and "current_letter_id" not in st.session_state:
        st.session_state.current_letter_id = jobs[-1]["letter_id"]

    job_options = [j["letter_id"] for j in jobs] if jobs else []
    if job_options:
        selected = st.selectbox(
            "Letter ID (jobs for your account):",
            job_options,
            index=job_options.index(st.session_state.get("current_letter_id", job_options[-1]))
            if st.session_state.get("current_letter_id") in job_options else len(job_options) - 1
        )
        st.session_state.current_letter_id = selected

    job = find_job_in_list(jobs, st.session_state.get("current_letter_id","")) if job_options else None

    if job:
        status = (job.get("status") or "").strip().lower()
        st.write(f"**Job status:** `{status}`  •  **Bureau:** {job.get('bureau','')}  •  **Type:** {job.get('dispute_type','')}  •  **Round:** {job.get('round','')}")
        qa_raw = job.get("qa_notes") or ""
        if qa_raw.strip():
            st.info("QA review notes:")
            st.code(qa_raw, language="json")

        cols = st.columns(3)
        with cols[0]:
            if st.button("🔄 Re-queue (fix & regenerate)"):
                try:
                    payload = job.get("payload_json")
                    try:
                        payload = json.loads(payload) if isinstance(payload, str) else payload
                    except Exception:
                        payload = None
                    requeue_job(job["letter_id"], payload=payload)
                    st.success("Re-queued. The worker will pick this up on the next cycle.")
                except Exception as e:
                    st.error(f"Could not re-queue: {e}")
        with cols[1]:
            st.write("")
        with cols[2]:
            st.caption(f"Created: {job.get('created_at_local','')}  •  Updated: {job.get('updated_at_local','')}")
    else:
        st.caption("No queued jobs yet for this account. Generate a letter to create one.")

    # ---------- defaults & login ----------
    st.session_state.setdefault("s8_generated", False)
    st.session_state.setdefault("law_selection", [])
    st.session_state.setdefault("dispute_details", {})

    user_obj = st.session_state.get("user") or {}
    if not user_obj:
        st.error("Please log in again.")
        st.stop()

    # ---------- PRE-GENERATION ----------
    if not st.session_state.s8_generated:
        agree = st.checkbox(
            "I understand that removed items may still represent valid debts and may still be owed.",
            key=_k("agree_cb")
        )

        cols = st.columns([1,1,3])
        with cols[0]:
            if st.button("Back to Step 7", key=_k("back_to7_btn")):
                st.session_state.step = 7
                st.rerun()

        with cols[1]:
            if st.button("Generate Letter", key=_k("generate_btn"), disabled=not agree):
                if not agree:
                    st.warning("Please check the disclaimer box first.")
                    st.stop()

                # --- guardrails & credits ---
                email = (
                    (st.session_state.get("user") or {}).get("email")
                    or st.session_state.get("user_email")
                    or st.session_state.get("email")
                    or ""
                )

                # Use cached Users sheet record to enforce daily/monthly caps
                user_rec = (st.session_state.get("user") or {}).get("record") or find_user(email) or {}

                # Block if out of credits (covers both daily & monthly according to PLAN_LIMITS)
                if not can_generate_letter(user_rec):
                    q = remaining_quota(user_rec)
                    st.error(
                        f"You're out of letter credits. "
                        f"Daily {q['daily_left']}/{q['daily_limit']} • "
                        f"Monthly {q['monthly_left']}/{q['monthly_limit']}"
                    )
                    st.stop()

                # Identity lock (keep your existing checks)
                user_info = st.session_state.get("user_info", {})
                if not lock_or_validate_user(user_info):
                    st.error(
                        "This subscription must be used only by the locked identity. "
                        "Confirm full name, DOB, and last 4 of SSN in Step 7."
                    )
                    st.stop()

                reason = cannot_spend_reason()
                if reason:
                    st.error(reason)
                    st.stop()

                # --- gather inputs ---
                dispute_details = st.session_state.dispute_details
                dispute_types = st.session_state.dispute_types
                bureau = st.session_state.get("selected_bureau", "")
                round_num = st.session_state.get("dispute_round", "Round 1")
                strategy  = st.session_state.get("round_strategy")
                law_selection = st.session_state.law_selection

                with st.spinner("Creating your personalized dispute letter..."):
                    try:
                        prompt = build_prompt(
                            user_info=user_info,
                            dispute_details=dispute_details,
                            dispute_types=dispute_types,
                            bureau=bureau,
                            round_num=round_num,
                            law_selection=law_selection,
                            strategy=strategy,
                        )
                    except TypeError:
                        prompt = build_prompt(
                            user_info=user_info,
                            dispute_details=dispute_details,
                            dispute_types=dispute_types,
                            bureau=bureau,
                            round_num=round_num,
                            law_selection=law_selection
                        )

                    resp = client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system",
                             "content": ("You are a credit repair expert. "
                                         "Return ONLY the body paragraphs of the dispute letter. "
                                         "No header, no date, no salutation, no signature.")},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.6,
                        max_tokens=900,
                    )
                    raw_body = (resp.choices[0].message.content or "").strip()
                    body = _strip_salutation_and_signature(raw_body)

                    # assemble final letter
                    full_name = user_info.get("full_name", "")
                    address = user_info.get("address", "")
                    city = user_info.get("city", "")
                    state = user_info.get("state", "")
                    zip_code = user_info.get("zip") or user_info.get("zip_code", "")
                    dob = user_info.get("dob", "")
                    ssn_last4 = user_info.get("ssn_last4", "")
                    bureau_block = BUREAU_ADDRESSES.get(bureau, bureau)
                    today_str = datetime.now().strftime("%B %d, %Y")

                    dob_line = f"Date of Birth: {dob}\n" if dob else ""
                    ssn_line = f"SSN Last 4: {ssn_last4}\n" if ssn_last4 else ""

                    header_block = (
                        f"{full_name}\n{address}\n{city}, {state} {zip_code}\n\n"
                        f"{dob_line}{ssn_line}\n"
                        f"{bureau_block}\n\n{today_str}\n\n"
                        f"Dear {bureau},\n"
                    )
                    signature = f"\nSincerely,\n{full_name}"
                    letter_text = f"{header_block}\n{body}{signature}"

                    # persist + history
                    st.session_state.generated_letter = letter_text
                    txt_path, pdf_path = save_letter_files(letter_text, full_name=full_name, bureau=bureau)
                    owner_email = (st.session_state.get("user") or {}).get("email", "")
                    _ = log_dispute(
                        full_name=full_name,
                        bureau=bureau,
                        round_num=round_num,
                        dispute_types=st.session_state.dispute_types,
                        txt_path=txt_path,
                        pdf_path=pdf_path,
                        owner_email=owner_email,
                    )

                    # increment Access counters + local sidebar credits
                    try:
                        email_for_log = (
                            (st.session_state.get("user") or {}).get("email")
                            or st.session_state.get("user_email")
                            or st.session_state.get("email")
                            or owner_email
                        )
                        dt = st.session_state.get("dispute_types") or []
                        dispute_type_str = ", ".join([str(x) for x in dt]) if isinstance(dt, (list, tuple)) else str(dt or "")
                        dd = st.session_state.get("dispute_details", {}) or {}
                        account_ref = dd.get("account_ref") or dd.get("account_number") or dd.get("creditor") or ""
                        letter_id_for_log = os.path.basename(txt_path) if txt_path else f"letter-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

                        increment_counters_and_log(
                            email=email_for_log,
                            bureau=bureau,
                            dispute_type=dispute_type_str,
                            account_ref=account_ref,
                            letter_id=letter_id_for_log,
                        )
                    except Exception as e:
                        st.warning(f"Logged locally; external usage log deferred ({e}).")

                    # local UI tracker
                    remaining = spend_one_credit()
                    if remaining == -1:
                        st.success("Letter generated. (Pro plan – unlimited credits)")
                    else:
                        st.success(f"Letter generated. Credits remaining: {remaining}")

                    # ✅ Users sheet counters (authoritative): deduct + refresh cached user, then rerun
                    try:
                        record_generation(user_rec)    # updates daily/monthly counters in Users sheet
                        refresh_cached_user()          # refreshes st.session_state.user['record'] for sidebar
                        st.session_state["__credits_updated__"] = True
                    except Exception as e:
                        # don't block user on display-only update
                        st.warning(f"Credits will update shortly ({e}).")

                    st.session_state.s8_generated = True
                    st.rerun()

        st.stop()

    # ---------- POST-GENERATION ----------
    letter_text = st.session_state.get("generated_letter", "")
    st.text_area("Your Generated Letter", letter_text, height=500, key=_k("preview_ta"))

    st.download_button(
        "Download as txt",
        data=letter_text,
        file_name="dispute_letter.txt",
        key=_k("dl_txt"),
    )

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for ln in letter_text.split("\n"):
        pdf.multi_cell(0, 10, _ascii_sanitize(ln))
    pdf_bytes = pdf.output(dest="S").encode("latin-1", "ignore")
    pdf_buffer = io.BytesIO(pdf_bytes)

    st.download_button(
        "Download as PDF",
        data=pdf_buffer,
        file_name="dispute_letter.pdf",
        mime="application/pdf",
        key=_k("dl_pdf"),
    )

    st.markdown("---")
    cols2 = st.columns([1,1,3])
    with cols2[0]:
        if st.button("Edit Step 7", key=_k("edit_step7")):
            st.session_state.s8_generated = False
            st.session_state.step = 7
            st.rerun()
    with cols2[1]:
        if st.button("Start Over", key=_k("start_over_btn")):
            for kclear in [
                "dispute_types","dispute_details","selected_bureau","dispute_round",
                "law_selection","user_info","generated_letter","help_chat","round_strategy"
            ]:
                st.session_state.pop(kclear, None)
            st.session_state.s8_generated = False
            st.session_state.step = 1
            st.rerun()
