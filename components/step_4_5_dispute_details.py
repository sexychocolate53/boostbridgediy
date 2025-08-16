import re
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.jobs import add_job_row   # <— new, avoids circular import

MAX_ITEMS = 5

def _digits_last4(s: str) -> str:
    s = "".join(ch for ch in (s or "") if ch.isdigit())
    return s[-4:] if s else ""

def _yyyy_mm(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    return s if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", s) else ""

def _new_letter_id():
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d-%H%M%S")
    user_slug = (st.session_state.get("user_full_name","user").strip().lower().replace(" ","-") or "user")
    bureau = (st.session_state.get("selected_bureau","") or "bureau").lower()
    return f"{user_slug}-{bureau}-{stamp}"

def _base_user():
    return {
        "full_name": st.session_state.get("user_full_name",""),
        "address":   st.session_state.get("user_address",""),
        "dob":       st.session_state.get("user_dob",""),
        "last4":     st.session_state.get("user_last4",""),
        "phone":     st.session_state.get("user_phone",""),
        "sms_opt_in": bool(st.session_state.get("user_sms_opt_in", False)),
    }


def render():
    st.header("📝 Step 4.5: Describe Your Dispute")

    dispute_types = st.session_state.get("dispute_types", [])
    if not dispute_types:
        st.error("No dispute type selected. Please go back.")
        if st.button("⬅️ Back"):
            st.session_state.step = 4
            st.rerun()
        return

    dtype = dispute_types[0].lower().replace(" ", "_")

    # ===================== ACCOUNT (multi-item, cap 5) =====================
    if dtype == "account":
        st.caption("You can bundle up to **5 accounts** in this one letter to the same bureau.")
        items = st.session_state.get("account_items", [])
        if not isinstance(items, list):
            items = []
        st.session_state.account_items = items
        st.session_state.setdefault("dispute_details", {})
        st.session_state.dispute_details["account_items"] = items

        # ---- Add new item form ----
        with st.form("add_account_item", clear_on_submit=True):
            a_name  = st.text_input("Account Name or Lender", key="f_ai_name")
            a_last4 = st.text_input("Last 4 of Account # (optional)", key="f_ai_last4", max_chars=8)
            a_issue = st.text_area("What is wrong with this account?", key="f_ai_issue", height=120)
            a_docs  = st.radio("Do you have documentation?", ["Yes", "No"], index=1, horizontal=True, key="f_ai_docs")
            c1, c2 = st.columns(2)
            with c1:
                a_dofd = st.text_input("First month you fell behind (YYYY-MM, optional)", key="f_ai_dofd")
            with c2:
                a_event = st.text_input("Charge-off/Collection month (YYYY-MM, optional)", key="f_ai_event")

            add_ok = st.form_submit_button("➕ Add to Letter", disabled=len(items) >= MAX_ITEMS)
            if add_ok:
                name = (a_name or "").strip()
                issue = (a_issue or "").strip()
                last4 = _digits_last4(a_last4)
                dofd  = _yyyy_mm(a_dofd)
                event = _yyyy_mm(a_event)
                if not name or not issue:
                    st.warning("Please enter at least the account name and what is wrong.")
                else:
                    items.append({
                        "name": name,
                        "last4": last4,
                        "issue": issue,
                        "docs": a_docs,
                        "dofd_ym": dofd,
                        "event_ym": event,
                    })
                    st.session_state.account_items = items
                    st.session_state.dispute_details["account_items"] = items
                    # pop keys is safe but not required due to clear_on_submit=True
                    for k in ("f_ai_name","f_ai_last4","f_ai_issue","f_ai_dofd","f_ai_event"):
                        st.session_state.pop(k, None)
                    st.success(f"Added **{name}**.")
                    st.rerun()

        # ---- Existing items list ----
        if items:
            st.subheader(f"Included in this letter ({len(items)}/{MAX_ITEMS})")
            for idx, it in enumerate(items):
                title = f"{idx+1}. {it.get('name','(unnamed)')} • Last4: {it.get('last4') or 'N/A'}"
                with st.expander(title, expanded=False):
                    ename  = st.text_input("Account Name or Lender", value=it.get("name",""), key=f"edit_name_{idx}")
                    elast4 = st.text_input("Last 4 (optional)", value=it.get("last4",""), key=f"edit_last4_{idx}", max_chars=8)
                    eissue = st.text_area("What is wrong with this account?", value=it.get("issue",""), key=f"edit_issue_{idx}", height=110)
                    edocs  = st.radio("Documentation?", ["Yes","No"],
                                      index=0 if (it.get("docs")=="Yes") else 1,
                                      horizontal=True, key=f"edit_docs_{idx}")
                    d1, d2 = st.columns(2)
                    with d1:
                        edofd  = st.text_input("First delinquency (YYYY-MM, optional)",
                                               value=it.get("dofd_ym",""), key=f"edit_dofd_{idx}")
                    with d2:
                        eevent = st.text_input("CO/Collection month (YYYY-MM, optional)",
                                               value=it.get("event_ym",""), key=f"edit_event_{idx}")

                    c1, c2 = st.columns(2)
                    if c1.button("💾 Save", key=f"save_{idx}"):
                        items[idx] = {
                            "name": (ename or "").strip(),
                            "last4": _digits_last4(elast4),
                            "issue": (eissue or "").strip(),
                            "docs": edocs,
                            "dofd_ym": _yyyy_mm(edofd),
                            "event_ym": _yyyy_mm(eevent),
                        }
                        st.session_state.account_items = items
                        st.session_state.dispute_details["account_items"] = items
                        st.success("Updated.")
                        st.rerun()
                    if c2.button("🗑️ Remove", key=f"remove_{idx}"):
                        items.pop(idx)
                        st.session_state.account_items = items
                        st.session_state.dispute_details["account_items"] = items
                        st.rerun()

        # ---- Nav ----
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Back"):
                st.session_state.step = 4
                st.rerun()
        with col2:
            if st.button("Save & Continue ➡️", disabled=len(items) == 0):
                # Ensure canonical storage
                st.session_state.dispute_details["account_items"] = items

                # Build payload for JOBS sheet (account type = multi items)
                payload = {
                    "user": _base_user(),
                    "items": items,
                    "bureau": st.session_state.get("selected_bureau",""),
                    "round":  st.session_state.get("round_name","R1"),
                    "notes":  st.session_state.get("notes","")
                }
                letter_id = _new_letter_id()
                add_job_row(
                    letter_id=letter_id,
                    email=st.session_state.get("email",""),
                    bureau=st.session_state.get("selected_bureau",""),
                    dispute_type="account",
                    round_name=st.session_state.get("round_name","R1"),
                    payload=payload
                )

                st.session_state.step = 5
                st.rerun()
        return

    # ===================== ALL OTHER TYPES (single item) =====================
    with st.form("details_form"):
        if dtype in {"hard_inquiry", "inquiry"}:
            inquiry_name = st.text_input("Who pulled your credit?", key="inquiry_name")
            inquiry_reason = st.text_area("Why is this inquiry unauthorized?", key="inquiry_reason")
            details = {"name": inquiry_name, "reason": inquiry_reason}
            item_for_queue = {"type": "inquiry", **details}

        elif dtype in {"personal_information", "personal_info"}:
            wrong_info = st.text_input("What info is incorrect?", key="wrong_info")
            correct_info = st.text_input("What should it be instead?", key="correct_info")
            details = {"wrong": wrong_info, "correct": correct_info}
            item_for_queue = {"type": "personal_info", **details}

        elif dtype == "public_record":
            record_type = st.selectbox("Type of public record?", ["Bankruptcy", "Tax Lien", "Judgment", "Other"], key="record_type")
            record_issue = st.text_area("What is wrong with this record?", key="record_issue")
            details = {"type": record_type, "issue": record_issue}
            item_for_queue = {"type": "public_record", **details}

        elif dtype == "duplicate":
            dup_name = st.text_input("Duplicate Account Name", key="dup_name")
            dup_details = st.text_area("Why do you think this is a duplicate?", key="dup_details")
            details = {"name": dup_name, "details": dup_details}
            item_for_queue = {"type": "duplicate", **details}

        elif dtype == "repo":
            repo_type = st.radio("Was this repo voluntary or involuntary?", ["Voluntary", "Involuntary"], key="repo_type")
            repo_issue = st.text_area("What is inaccurate about the repo?", key="repo_issue")
            details = {"type": repo_type, "issue": repo_issue}
            item_for_queue = {"type": "repo", **details}

        elif dtype == "mixed_file":
            mixed_issue = st.text_area("Describe what doesn't belong to you.", key="mixed_issue")
            details = {"issue": mixed_issue}
            item_for_queue = {"type": "mixed_file", **details}

        elif dtype == "reinserted":
            reinsert_details = st.text_area("What was removed and reappeared?", key="reinserted_details")
            details = {"details": reinsert_details}
            item_for_queue = {"type": "reinserted", **details}

        else:
            other_desc = st.text_area("Describe your issue", key="other_details")
            details = {"details": other_desc}
            item_for_queue = {"type": "other", **details}

        submitted = st.form_submit_button("✅ Save & Continue")
        if submitted:
            # Save normal page state
            st.session_state.setdefault("dispute_details", {})
            st.session_state.dispute_details[dtype] = details

            # Queue a single-item payload for JOBS
            payload = {
                "user": _base_user(),
                "items": [item_for_queue],
                "bureau": st.session_state.get("selected_bureau",""),
                "round":  st.session_state.get("round_name","R1"),
                "notes":  st.session_state.get("notes","")
            }
            letter_id = _new_letter_id()
            add_job_row(
                letter_id=letter_id,
                email=st.session_state.get("email",""),
                bureau=st.session_state.get("selected_bureau",""),
                dispute_type=dtype,
                round_name=st.session_state.get("round_name","R1"),
                payload=payload
            )

            st.session_state.step = 5
            st.rerun()

    if st.button("⬅️ Back"):
        st.session_state.dispute_types = []
        st.session_state.step = 4
        st.rerun()
