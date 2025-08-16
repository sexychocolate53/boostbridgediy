import re
import streamlit as st
from utils.credit_tracker import lock_or_validate_user
from utils.profile_store import get_profile, save_profile

DOB_HELP = "We only need month/year (MM/YYYY) or just the year (YYYY). Do not enter the day."
PHONE_HELP = "Optional. Digits only are fine — we'll format it for SMS. Example: 9045551212."

def _normalize_dob(value: str) -> str:
    """
    Accepts:
      - 'MM/YYYY' (01–12 for MM)
      - 'YYYY'
      - blank
    Returns normalized 'MM/YYYY' or 'YYYY' or '' if invalid.
    """
    v = (value or "").strip()
    if not v:
        return ""
    v = v.replace("\\", "/").replace("-", "/")
    if re.fullmatch(r"(0[1-9]|1[0-2])/(19|20)\d{2}", v):
        return v
    if re.fullmatch(r"(19|20)\d{2}", v):
        return v
    return ""  # invalid

def _normalize_phone(value: str) -> str:
    """
    Return E.164-ish normalized phone for SMS or '' if clearly invalid/too short.
    Rules:
      - Keep digits and '+' only.
      - If 10 digits, assume US and prefix +1.
      - If 11 digits starting with '1', prefix '+'.
      - If starts with '+', keep as-is (digits only after '+').
    """
    v = (value or "").strip()
    if not v:
        return ""
    # keep + and digits
    raw = "".join(ch for ch in v if ch.isdigit() or ch == "+")
    if not raw:
        return ""
    if raw.startswith("+"):
        # "+1XXXXXXXXXX" or other country codes — basic sanity: must have at least 11 chars including '+'
        return raw if len(raw) >= 11 else ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits[0] == "1":
        return "+" + digits
    # If longer than 11, assume it includes country code (no + provided)
    if len(digits) > 10:
        return "+" + digits
    return ""  # too short to be a mobile

def render():
    st.header("Step 7: Enter Your Personal Information")
    st.markdown("Please provide your personal details exactly as you'd like them to appear in your letter.")

    # --- who is this? (needed for profile store) ---
    email = (
        (st.session_state.get("user") or {}).get("email")
        or st.session_state.get("user_email")
        or st.session_state.get("email")
        or ""
    )

    # Initialize user_info and prefill from persisted profile (session wins)
    persisted = get_profile(email) if email else {}
    if "user_info" not in st.session_state or not isinstance(st.session_state.user_info, dict):
        st.session_state.user_info = {}
    base = {**persisted, **(st.session_state.user_info or {})}

    with st.form("user_info_form"):
        full_name = st.text_input("Full Name", value=base.get("full_name", ""), key="user_full_name")
        address   = st.text_input("Street Address", value=base.get("address", ""), key="user_address")
        city      = st.text_input("City", value=base.get("city", ""), key="user_city")
        state     = st.text_input("State (2 letters)", value=base.get("state", ""), key="user_state")
        # accept either saved key
        zip_code  = st.text_input("ZIP Code", value=base.get("zip_code", "") or base.get("zip",""), key="user_zip_code")

        # ✅ optional phone + SMS opt-in
        phone_in  = st.text_input("Mobile phone (optional, for reminders)", value=base.get("phone",""), key="user_phone", help=PHONE_HELP)
        sms_opt   = st.checkbox("OK to receive SMS reminders about my disputes", value=bool(base.get("sms_opt_in", False)), key="user_sms_opt_in")

        dob_raw   = st.text_input("Date of Birth (MM/YYYY or YYYY)", value=base.get("dob", ""), key="user_dob", help=DOB_HELP)
        ssn_last4 = st.text_input("Last 4 digits of SSN", max_chars=4, value=base.get("ssn_last4", ""), key="user_ssn_last4")

        submitted = st.form_submit_button("➡️ Next")
        if submitted:
            dob_norm   = _normalize_dob(dob_raw)
            phone_norm = _normalize_phone(phone_in)

            # save draft to session
            st.session_state.user_info = {
                "full_name": full_name.strip(),
                "address":   address.strip(),
                "city":      city.strip(),
                "state":     state.strip(),
                "zip_code":  zip_code.strip(),
                "zip":       zip_code.strip(),   # also store 'zip' for downstream compatibility
                "dob":       dob_norm,           # normalized month/year or year
                "ssn_last4": ssn_last4.strip(),
                "phone":     phone_norm,
                "sms_opt_in": bool(sms_opt),
            }

            # gentle warning if they typed a phone but it didn't normalize
            if phone_in.strip() and not phone_norm:
                st.warning("That phone number didn’t look valid. You can leave it blank or enter 10 digits (e.g., 9045551212).")

            # minimal validation: name + SOME dob format + ssn4
            if not st.session_state.user_info["full_name"]:
                st.error("Please enter your Full Name.")
            elif dob_raw and not dob_norm:
                st.error("DOB format must be MM/YYYY (e.g., 08/1988) or YYYY (e.g., 1988).")
            elif not st.session_state.user_info["dob"]:
                # If you want DOB to be optional, comment this block out:
                st.error("Please enter your Date of Birth as MM/YYYY or YYYY.")
            elif len(st.session_state.user_info["ssn_last4"]) != 4 or not st.session_state.user_info["ssn_last4"].isdigit():
                st.error("SSN Last 4 must be exactly 4 digits.")
            else:
                # lock or validate identity (prevents “friends” usage)
                ok = lock_or_validate_user(st.session_state.user_info)
                if not ok:
                    st.error("Identity could not be locked. Make sure Full Name, DOB (MM/YYYY or YYYY), and SSN Last 4 are filled in.")
                else:
                    # ✅ persist on success so it’s there on next login/restart
                    if email:
                        try:
                            save_profile(email, st.session_state.user_info)
                            st.toast("Personal info saved to your account.")
                        except Exception as e:
                            st.warning(f"Saved for this session; profile persistence deferred ({e}).")

                    st.session_state.step = 7.5
                    st.rerun()

    if st.button("⬅️ Back"):
        st.session_state.step = 6
        st.rerun()
