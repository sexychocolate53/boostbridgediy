import streamlit as st

def render():
    st.header("Step 3: Choose a Credit Bureau")

    bureaus = [
        "Equifax",
        "Experian",
        "TransUnion",
        "LexisNexis",
        "SageStream",
        "Innovis",
        "CoreLogic",
        "ChexSystems",
        "NCTUE",
        "Clarity Services"
    ]

    # Use a unique key so you never get duplicate widget errors
    selected = st.radio(
        "Which credit bureau are you disputing with?",
        bureaus,
        key="selected_bureau_widget"
    )

    st.markdown(f"#### 📌 Bureau Selected: **{selected}**")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Back"):
            st.session_state.step = 2
            st.session_state.selected_bureau = None
            st.session_state.dispute_types = []
            st.session_state.dispute_details = {}
            st.rerun()
    with col2:
        if st.button("Next ➡️"):
            # On Next, save and always clear following steps for a fresh start
            st.session_state.selected_bureau = selected
            st.session_state.dispute_types = []
            st.session_state.dispute_details = {}
            st.session_state.user_info = {}
            st.session_state.step = 4  # always to the dispute type picker
            st.rerun()
