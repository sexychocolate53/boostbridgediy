# utils/credit_tracker.py
import streamlit as st
import re

# How many credits an Individual starts with
DEFAULT_INDIVIDUAL_CREDITS = 15

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def make_user_key(user_info: dict) -> str:
    """Stable key for this person's subscription (name + dob + ssn_last4)."""
    full_name = _norm(user_info.get("full_name", ""))
    dob = _norm(user_info.get("dob", ""))
    ssn = _norm(user_info.get("ssn_last4", ""))
    return f"{full_name}|{dob}|{ssn}"

def init_tracker_if_needed(mode: str = "individual"):
    """
    Ensure credit tracker exists in session.
    mode: "individual" or "pro"
    """
    st.session_state.setdefault("credit_mode", mode)
    # For pro, we don't enforce credits
    if mode == "pro":
        st.session_state["credits_remaining"] = None
        st.session_state["locked_user_key"] = None
        return

    # Individual defaults
    st.session_state.setdefault("credits_remaining", DEFAULT_INDIVIDUAL_CREDITS)
    st.session_state.setdefault("locked_user_key", None)

def lock_or_validate_user(user_info: dict) -> bool:
    """
    On first use, lock the subscription to the user's identity (name+dob+ssn).
    On later uses, ensure current identity matches the locked identity.
    Returns True if OK, False if mismatch.
    """
    if st.session_state.get("credit_mode") == "pro":
        return True  # pro accounts are not locked to a single identity

    key_now = make_user_key(user_info)
    locked = st.session_state.get("locked_user_key")

    # If we have no lock yet, set it—BUT only if key is not empty
    if not locked:
        if key_now.strip("|") == "" or "||" in key_now:
            # Missing fields; we can't lock yet
            return False
        st.session_state["locked_user_key"] = key_now
        return True

    # Already locked: must match
    return locked == key_now

def cannot_spend_reason() -> str | None:
    """Return reason string if user cannot spend credit, else None."""
    if st.session_state.get("credit_mode") == "pro":
        return None
    remaining = st.session_state.get("credits_remaining", 0)
    if remaining <= 0:
        return "No credits remaining."
    return None

def spend_one_credit() -> int:
    """
    Deduct a single credit (individual mode only).
    Returns the remaining credits.
    """
    if st.session_state.get("credit_mode") == "pro":
        return -1  # Unlimited for pro; ignore
    st.session_state["credits_remaining"] = max(0, int(st.session_state.get("credits_remaining", 0)) - 1)
    return st.session_state["credits_remaining"]

def render_sidebar_badge():
    """Small badge in the sidebar to show plan + credits."""
    mode = st.session_state.get("credit_mode", "individual")
    st.sidebar.markdown("### 💼 Plan")
    st.sidebar.write("**Pro (Unlimited)**" if mode == "pro" else "**Individual**")

    if mode == "individual":
        rem = st.session_state.get("credits_remaining", 0)
        st.sidebar.markdown("### 🎟️ Letter Credits")
        st.sidebar.metric(label="Remaining", value=rem)
        st.sidebar.progress(min(1.0, max(0.0, rem / float(DEFAULT_INDIVIDUAL_CREDITS))))
