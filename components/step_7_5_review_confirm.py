# components/step_7_5_review_confirm.py
import streamlit as st
from datetime import datetime

def _mask_last4(s: str) -> str:
    s = (s or "").strip()
    return f"•••• {s[-4:]}" if s else "—"

def _mmmyyyy(d: str) -> str:
    # accept "MM/DD/YYYY" or "MM/YYYY" or "YYYY-MM"
    d = (d or "").strip()
    if not d:
        return ""
    try:
        if "-" in d and len(d) == 7:  # YYYY-MM
            return datetime.strptime(d, "%Y-%m").strftime("%b %Y")
        if "/" in d and len(d) == 10:  # MM/DD/YYYY
            return datetime.strptime(d, "%m/%d/%Y").strftime("%b %Y")
        if "/" in d and len(d) == 7:   # MM/YYYY
            return datetime.strptime(d, "%m/%Y").strftime("%b %Y")
    except Exception:
        pass
    return d  # fallback as-is

def _render_items():
    dd = st.session_state.get("dispute_details", {}) or {}

    # multi-account path
    items = dd.get("account_items")
    if isinstance(items, list) and items:
        for idx, it in enumerate(items[:5], start=1):
            with st.expander(f"{idx}. {it.get('name','(unnamed)')} • Last4: {it.get('last4') or 'N/A'}", expanded=False):
                st.write(f"**Issue:** {it.get('issue','') or '—'}")
                st.write(f"**Docs:** {it.get('docs','') or '—'}")
                st.write(f"**DOFD (YYYY-MM):** {it.get('dofd_ym','') or '—'}")
                st.write(f"**Event (YYYY-MM):** {it.get('event_ym','') or '—'}")
        return

    # single-type path
    types = st.session_state.get("dispute_types", []) or []
    t = (types[0].lower().replace(" ", "_") if types else "")
    info = dd.get(t, {}) if isinstance(dd.get(t, {}), dict) else dd

    if t in {"hard_inquiry", "inquiry"}:
        st.write(f"**Type:** Hard Inquiry")
        st.write(f"**Creditor:** {info.get('name','') or '—'}")
        st.write(f"**Reason (unauthorized):** {info.get('reason','') or '—'}")
    elif t in {"personal_information", "personal_info"}:
        st.write("**Type:** Personal Information")
        st.write(f"**Incorrect:** {info.get('wrong','') or '—'}")
        st.write(f"**Should be:** {info.get('correct','') or '—'}")
    elif t == "public_record":
        st.write("**Type:** Public Record")
        st.write(f"**Record:** {info.get('type','') or '—'}")
        st.write(f"**Issue:** {info.get('issue','') or '—'}")
    elif t == "duplicate":
        st.write("**Type:** Duplicate Tradeline")
        st.write(f"**Name:** {info.get('name','') or '—'}")
        st.write(f"**Why duplicate:** {info.get('details','') or '—'}")
    elif t == "repo":
        st.write("**Type:** Repossession")
        st.write(f"**Voluntary?:** {info.get('type','') or '—'}")
        st.write(f"**Issue:** {info.get('issue','') or '—'}")
    elif t == "mixed_file":
        st.write("**Type:** Mixed File")
        st.write(f"**Not mine / wrong info:** {info.get('issue','') or '—'}")
    elif t == "reinserted":
        st.write("**Type:** Reinserted Item")
        st.write(f"**Details:** {info.get('details','') or '—'}")
    else:
        st.write("**Type:** Other")
        st.write(f"**Details:** {info.get('details','') or '—'}")

def render():
    st.header("Step 7.5: Review & Confirm")

    # guard: ensure prior steps exist
    needed = ["dispute_types", "dispute_details", "selected_bureau", "user_info"]
    if not all(st.session_state.get(k) for k in needed):
        st.warning("Some info is missing; sending you to Step 1 to restart.")
        st.session_state.step = 1
        st.rerun()
        return

    user = st.session_state.get("user_info", {}) or {}
    bureau = st.session_state.get("selected_bureau", "")
    round_name = st.session_state.get("round_name") or st.session_state.get("dispute_round") or "Round 1"
    strategy = st.session_state.get("round_strategy") or "—"
    types = st.session_state.get("dispute_types", []) or []

    # summary cards
    st.subheader("Your Details")
    # after: st.subheader("Your Details")
    c1, c2, c3 = st.columns([1.4, 1, 1])
    with c1:
        st.write(f"**Name**: {user.get('full_name','') or '—'}")
        st.write(f"**Address**: {user.get('address','') or '—'}")
        st.write(f"**City/State/ZIP**: {user.get('city','') or '—'}, "
                f"{user.get('state','') or '—'} "
                f"{user.get('zip_code','') or user.get('zip','') or '—'}")
    with c2:
        dob = user.get("dob","")
        st.write(f"**DOB (shown as)**: {_mmmyyyy(dob) or '—'}")
        st.write(f"**Phone**: {user.get('phone','') or '—'}")              # <-- add
    with c3:
        st.write(f"**SSN Last 4**: {_mask_last4(user.get('ssn_last4',''))}")
        st.write(f"**SMS Opt-in**: {'Yes' if user.get('sms_opt_in') else 'No'}")  # <-- add


    st.subheader("Letter Setup")
    c4, c5, c6 = st.columns([1, 1, 2])
    with c4:
        st.write(f"**Bureau**: {bureau or '—'}")
    with c5:
        st.write(f"**Round**: {round_name}")
    with c6:
        st.write(f"**Strategy**: {strategy}")

    st.subheader("Dispute Items")
    _render_items()

    # edit shortcuts
    st.markdown("---")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        if st.button("✏️ Edit Dispute Type/Items (Step 4–4.5)"):
            st.session_state.step = 4
            st.rerun()
    with e2:
        if st.button("✏️ Edit Bureau (Step 3)"):
            st.session_state.step = 3
            st.rerun()
    with e3:
        if st.button("✏️ Edit Round/Strategy (Step 5–6)"):
            st.session_state.step = 5
            st.rerun()
    with e4:
        if st.button("✏️ Edit Personal Info (Step 7)"):
            st.session_state.step = 7
            st.rerun()

    st.markdown("---")
    confirm = st.checkbox("I confirm the above information is accurate and I want to generate my letter.")

    cA, cB = st.columns([1, 1])
    with cA:
        if st.button("⬅️ Back to Step 7"):
            st.session_state.step = 7
            st.rerun()
    with cB:
        if st.button("Generate Letter ➡️", disabled=not confirm):
            st.session_state.step = 8
            st.rerun()
