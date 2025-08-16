import os
import streamlit as st
import pandas as pd
from utils.tips import tips_from_history_row
from utils.history import load_history, update_status, STATUS_CHOICES

def _current_user_email() -> str | None:
    u = st.session_state.get("user")
    return (u or {}).get("email")

def _which_email_col(df: pd.DataFrame) -> str | None:
    for c in ["owner_email", "email", "user_email", "created_by"]:
        if c in df.columns:
            return c
    return None

def _download_button_for(path: str, label: str, key: str, allowed: bool):
    if not allowed:
        st.button(f"{label} (not allowed)", key=f"{key}_deny", disabled=True)
        return
    if not path or not os.path.exists(path):
        st.button(f"{label} (missing)", key=f"{key}_missing", disabled=True)
        return
    with open(path, "rb") as f:
        st.download_button(label, data=f.read(), file_name=os.path.basename(path), key=key)

def render():
    st.header("📜 Dispute History")

    cur_email = _current_user_email()
    if not cur_email:
        st.error("Please log in to view your history.")
        st.stop()

    df = load_history()
    if df is None or df.empty:
        st.info("No letters have been generated yet.")
        st.markdown("---")
        if st.button("🔄 Start Over", key="hist_start_over_empty"):
            st.session_state.clear()
            st.session_state.step = 1
            st.rerun()
        return

    email_col = _which_email_col(df)
    if not email_col:
        st.error("History does not include an owner email column. Please add 'owner_email' when logging disputes.")
        st.stop()

    view = df[df[email_col].str.strip().str.lower() == cur_email.strip().lower()].copy()

    if view.empty:
        st.info("You don’t have any saved letters yet.")
        st.markdown("---")
        colA, colB = st.columns(2)
        with colA:
            if st.button("🏠 Back to Start", key="hist_back_to_start_empty"):
                st.session_state.step = 1
                st.rerun()
        with colB:
            if st.button("📝 New Letter", key="hist_new_letter_empty"):
                st.session_state.step = 2
                st.rerun()
        return

    cols = st.columns(4)
    with cols[0]:
        f_bureau = st.selectbox("Bureau", options=["All"] + sorted(view["bureau"].dropna().unique().tolist()),
                                key="hist_f_bureau")
    with cols[1]:
        f_status = st.selectbox("Status", options=["All"] + sorted(view["status"].dropna().unique().tolist()),
                                key="hist_f_status")
    with cols[2]:
        f_name = st.text_input("Search name", key="hist_f_name")
    with cols[3]:
        if st.button("Clear Filters", key="hist_clear_filters"):
            st.rerun()

    filtered = view.copy()
    if f_bureau != "All":
        filtered = filtered[filtered["bureau"] == f_bureau]
    if f_status != "All":
        filtered = filtered[filtered["status"] == f_status]
    if f_name.strip():
        filtered = filtered[filtered["full_name"].str.contains(f_name.strip(), case=False, na=False)]

    if filtered.empty:
        st.info("No results match your filters.")
    else:
        for idx, row in filtered.sort_values("created_at", ascending=False).iterrows():
            row_id = str(row.get("id", f"row_{idx}"))
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 2, 2, 3])

                with c1:
                    st.markdown(f"**Name:** {row.get('full_name','')}")
                    st.caption(str(row.get("created_at","")))

                with c2:
                    st.markdown(f"**Bureau:** {row.get('bureau','')}")
                    st.markdown(f"**Round:** {row.get('round','')}")

                with c3:
                    st.markdown(f"**Types:** {row.get('dispute_types','')}")
                    st.markdown(f"**Status:** {row.get('status','')}")
                    current_status = row.get("status", STATUS_CHOICES[0])
                    new_status = st.selectbox(
                        "Update status",
                        options=STATUS_CHOICES,
                        index=STATUS_CHOICES.index(current_status) if current_status in STATUS_CHOICES else 0,
                        key=f"hist_status_{row_id}"
                    )
                    if st.button("Save", key=f"hist_save_{row_id}"):
                        ok = update_status(row["id"], new_status)
                        (st.success if ok else st.error)("Status updated." if ok else "Could not update status.")
                        st.rerun()

                with c4:
                    st.markdown("**Downloads**")
                    allowed = str(row.get(email_col,"")).strip().lower() == cur_email.strip().lower()
                    _download_button_for(row.get("txt_path",""), "TXT", key=f"hist_txt_{row_id}", allowed=allowed)
                    _download_button_for(row.get("pdf_path",""), "PDF", key=f"hist_pdf_{row_id}", allowed=allowed)

                    st.markdown("---")
                    if st.button("🎓 Tips for this", key=f"hist_tips_{row_id}"):
                        ctx = tips_from_history_row(row)
                        st.session_state["edu_context"] = ctx
                        st.session_state.step = 98
                        st.rerun()

    st.markdown("---")
    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("🏠 Back to Start", key="hist_back_to_start"):
            st.session_state.step = 1
            st.rerun()
    with colB:
        if st.button("📝 New Letter", key="hist_new_letter"):
            st.session_state.step = 2
            st.rerun()
