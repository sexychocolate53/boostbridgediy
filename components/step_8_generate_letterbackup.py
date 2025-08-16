import streamlit as st
from utils.prompt_builder import build_prompt
from openai import OpenAI
from dotenv import load_dotenv
import os, io, re
from datetime import datetime
from fpdf import FPDF
from utils.history import save_letter_files, log_dispute
from utils.auth import can_generate_letter, record_generation
from utils.access_gate import increment_counters_and_log   # <-- NEW
from utils.credit_tracker import (
    lock_or_validate_user,
    cannot_spend_reason,
    spend_one_credit,
)

# --- setup ---
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

def _build_personal_info_issue_list(dd: dict) -> list[str]:
    out = []
    wrong_addr = dd.get("wrong_address") or dd.get("reported_address")
    correct_addr = dd.get("correct_address")
    if wrong_addr or correct_addr:
        out.append(f"Address — reported as '{wrong_addr or 'N/A'}' but correct is '{correct_addr or 'N/A'}'")

    wrong_name = dd.get("wrong_name") or dd.get("name_variation")
    correct_name = dd.get("correct_name")
    if wrong_name or correct_name:
        out.append(f"Name variation — reported as '{wrong_name or 'N/A'}' but legal name is '{correct_name or 'N/A'}'")

    wrong_job = dd.get("wrong_employer") or dd.get("reported_employer")
    correct_job = dd.get("correct_employer")
    if wrong_job or correct_job:
        out.append(f"Employment — reported as '{wrong_job or 'N/A'}' but correct employer is '{correct_job or 'N/A'}'")

    # Add phones/DOB/SSN etc. if you collect them
    return out


BUREAU_ADDRESSES = {
    "Equifax": "Equifax Information Services LLC\nP.O. Box 740256\nAtlanta, GA 30374",
    "Experian": "Experian\nP.O. Box 4500\nAllen, TX 75013",
    "TransUnion": "TransUnion Consumer Solutions\nP.O. Box 2000\nChester, PA 19016-2000",
}

def _strip_salutation_and_signature(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^(?:\s*(?:dear\b[^\n]*,|to whom[^\n]*,?|hello[^\n]*,?)\s*\n)+','',t,flags=re.IGNORECASE).lstrip()
    t = re.sub(r'\n\s*(?:dear\b[^\n]*,|to whom[^\n]*,?|hello[^\n]*,?)\s*\n','\n',t,flags=re.IGNORECASE)
    t = re.split(r'\n\s*(?:sincerely|regards|respectfully)\b.*', t, flags=re.IGNORECASE)[0].rstrip()
    return re.sub(r'\n{3,}', '\n\n', t)

def render():
    st.header("Step 8: Generate Your Letter")

    def k(name: str) -> str:
        return f"s8_{name}"

    # state
    st.session_state.setdefault("s8_generated", False)
    st.session_state.setdefault("law_selection", [])
    st.session_state.setdefault("dispute_round", "Round 1")
    st.session_state.setdefault("dispute_details", {})

    # ---------------- NEW: Guidance & flow controls ----------------
    with st.expander("How to use this the smart way (read this 👇)", expanded=False):
        st.markdown(
            "- **Personal Info cleanup** first (old addresses, names, employers). This is a pre-step, not a round.\n"
            "- **Round 1**: Friendly investigation — say items are **unfamiliar**; don’t overclaim.\n"
            "- **Round 2**: Choose **MOV** (how did you verify?) **or** **Factual** (specific errors like monthly charge-off updates / Metro 2).\n"
            "- **Round 3**: Send the **other** one you didn’t use in Round 2.\n"
            "- Don’t dispute too many accounts at once."
        )

    cols_top = st.columns([1,1,2])
    with cols_top[0]:
        round_choice = st.selectbox(
            "Dispute phase",
            ["Personal Info", "Round 1", "Round 2", "Round 3"],
            index=1,
            key=k("round_choice")
        )
    with cols_top[1]:
        strategy = None
        if round_choice in ["Round 2", "Round 3"]:
            strat_label = st.radio(
                "Round strategy",
                ["Method of Verification (MOV)", "Factual"],
                index=0,
                key=k("strategy")
            )
            strategy = "mov" if strat_label.startswith("Method") else "factual"
        else:
            strategy = None
    # keep original state key for compatibility with rest of app
    st.session_state.dispute_round = round_choice
    # --------------- END NEW -------------------

    # logged-in user record (for plan limits)
    user_obj = st.session_state.get("user") or {}
    user_record = user_obj.get("record") or {}
    if not user_record:
        st.error("Please log in again.")
        st.stop()

    # ---------- PRE-GENERATION ----------
    if not st.session_state.s8_generated:
        agree = st.checkbox(
            "I understand that removed items may still represent valid debts and may still be owed.",
            key=k("agree_cb")
        )

        cols = st.columns([1,1,3])
        with cols[0]:
            if st.button("Back to Step 7", key=k("back_to7_btn")):
                st.session_state.step = 7
                st.rerun()

        with cols[1]:
            if st.button("Generate Letter", key=k("generate_btn"), disabled=not agree):
                if not agree:
                    st.warning("Please check the disclaimer box first.")
                    st.stop()

                # --- guardrails BEFORE calling the model ---
                if not can_generate_letter(user_record):
                    st.error("You’ve reached your plan limit. Upgrade to continue.")
                    st.stop()

                user_info = st.session_state.get("user_info", {})
                if not lock_or_validate_user(user_info):
                    st.error("This subscription must be used only by the locked identity. "
                             "Confirm full name, DOB, and last 4 of SSN in Step 7.")
                    st.stop()

                reason = cannot_spend_reason()
                if reason:
                    st.error(reason)
                    st.stop()

                # --- generate letter ---
                dispute_details = st.session_state.dispute_details
                dispute_types = st.session_state.dispute_types
                bureau = st.session_state.get("selected_bureau", "")
                round_num = st.session_state.get("dispute_round", "Round 1")
                law_selection = st.session_state.law_selection

                with st.spinner("Creating your personalized dispute letter..."):
                    # Build prompt (compat: try with strategy, fall back if your builder isn't updated yet)
                    round_num = st.session_state.get("dispute_round", "Round 1")
                    strategy  = st.session_state.get("round_strategy")

                    try:
                        prompt = build_prompt(
                            user_info=user_info,
                            dispute_details=dispute_details,
                            dispute_types=dispute_types,
                            bureau=bureau,
                            round_num=round_num,
                            law_selection=law_selection,
                            strategy=strategy,  # from Step 5
                        )
                    except TypeError:
                        # fallback if your build_prompt has no `strategy` param yet
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

                    header_block = (
                        f"{full_name}\n{address}\n{city}, {state} {zip_code}\n\n"
                        f"Date of Birth: {dob}\nSSN Last 4: {ssn_last4}\n\n"
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
                        owner_email=owner_email,   # stored in CSV
                    )

                    # counters
                    record_generation(user_record)        # sheet daily/monthly
                    remaining = spend_one_credit()        # local sidebar credits

                    # >>> NEW: Log to the *separate* "BoostBridgeDIY Access" workbook and increment usage <<<
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
                        letter_id = os.path.basename(txt_path) if txt_path else f"letter-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

                        increment_counters_and_log(
                            email=email_for_log,
                            bureau=bureau,
                            dispute_type=dispute_type_str,
                            account_ref=account_ref,
                            letter_id=letter_id,
                        )
                    except Exception as e:
                        st.warning(f"Logged locally; external usage log deferred ({e}).")
                    # >>> END NEW <<<

                    if remaining == -1:
                        st.success("Letter generated. (Pro plan – unlimited credits)")
                    else:
                        st.success(f"Letter generated. Credits remaining: {remaining}")

                    st.session_state.s8_generated = True
                    st.rerun()
        return

    # ---------- POST-GENERATION ----------
    letter_text = st.session_state.get("generated_letter", "")
    st.text_area("Your Generated Letter", letter_text, height=500, key=k("preview_ta"))

    # txt download
    st.download_button("Download as txt", data=letter_text,
                       file_name="dispute_letter.txt", key=k("dl_txt"))

    # pdf download (ASCII-safe core font)
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
        key="s8_dl_pdf",
    )

    st.markdown("---")
    cols2 = st.columns([1,1,3])
    with cols2[0]:
        if st.button("Edit Step 7", key=k("edit_step7")):
            st.session_state.s8_generated = False
            st.session_state.step = 7
            st.rerun()
    with cols2[1]:
        if st.button("Start Over", key=k("start_over_btn")):
            for kclear in [
                "dispute_types","dispute_details","selected_bureau","dispute_round",
                "law_selection","user_info","generated_letter","help_chat"
            ]:
                st.session_state.pop(kclear, None)
            st.session_state.s8_generated = False
            st.session_state.step = 1
            st.rerun()
