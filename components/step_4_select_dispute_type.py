import streamlit as st

def render():
    st.header("📝 Step 4: Select Dispute Type")

    # Always let user select if nothing picked yet
    if not st.session_state.get("dispute_types"):
        options = [
            "Account (charge-offs, collections, etc.)",
            "Inquiry",
            "Personal Info",
            "Public Record",
            "Duplicate Account",
            "Repo",
            "Mixed File",
            "Reinserted Item",
            "Other"
        ]
        dispute_type = st.radio("Which issue are you disputing?", options, key="dispute_type_select")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Back"):
                st.session_state.step = 3
                st.rerun()
        with col2:
            if st.button("Next ➡️"):
                # Always use a clear, consistent key
                slug_map = {
                    "Account (charge-offs, collections, etc.)": "account",
                    "Inquiry": "inquiry",
                    "Personal Info": "personal_info",
                    "Public Record": "public_record",
                    "Duplicate Account": "duplicate",
                    "Repo": "repo",
                    "Mixed File": "mixed_file",
                    "Reinserted Item": "reinserted",
                    "Other": "other"
                }
                st.session_state.dispute_types = [slug_map[dispute_type]]
                st.session_state.step = 4.5
                st.rerun()
        return

    # If already picked, show info and let user reset if needed
    picked = st.session_state.dispute_types[0].replace("_", " ").title()
    st.info(f"Dispute type selected: **{picked}**")
    if st.button("🔄 Reset Dispute Type"):
        st.session_state.dispute_types = []
        st.rerun()

    # after user picks a type...
if st.button("Continue"):
    st.session_state.dispute_types = [choice]   # keep the selection
    st.session_state.step = 4.5                 # <-- this is the jump
    st.rerun()

