import streamlit as st

def render():
    st.header("Step 6: Select Supporting Laws")

    st.markdown("📜 Choose how you want to include legal statutes in your dispute letter:")

    # Step 1: Ask how they'd like to proceed
    law_mode = st.radio(
        "Would you like to select the laws or let the AI decide?",
        options=["Let the AI choose", "I'll choose myself"],
        key="law_mode"
    )

    # Step 2A: Manual selection
    if law_mode == "I'll choose myself":
        options = [
            "FCRA 611 - Investigation of Disputes",
            "FCRA 609 - Request for Information",
            "FCRA 602 - Purpose of Credit Reporting",
            "FDCPA - Fair Debt Collection Practices Act",
            "15 USC 1681i - Reinvestigation Requirements",
            "15 USC 1681s-2 - Responsibilities of Furnishers"
        ]
        selected_laws = st.multiselect("✅ Select applicable laws:", options)

        # ✅ Store in session_state
        st.session_state["law_selection"] = selected_laws

    # Step 2B: AI chooses
    else:
        st.info("✅ AI will automatically choose the best laws based on your dispute details.")
        # ✅ Initialize as empty list
        st.session_state["law_selection"] = []

    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Back"):
            st.session_state.step = 5
    with col2:
        if st.button("➡️ Next"):
            st.session_state.step = 7
