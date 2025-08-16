import streamlit as st

def render():
    st.header("Step 5: Select Dispute Round")

    if "dispute_round" not in st.session_state:
        st.session_state.dispute_round = "Round 1"

    round_choice = st.radio(
        "What round of dispute is this?",
        ["Round 1", "Round 2", "Round 3", "Final Notice"],
        index=["Round 1", "Round 2", "Round 3", "Final Notice"].index(st.session_state.dispute_round),
        key="dispute_round"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Back"):
            st.session_state.step = 4
    with col2:
        if st.button("➡️ Next"):
            st.session_state.step = 6
