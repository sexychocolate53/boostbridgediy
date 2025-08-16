import streamlit as st

def render():
    st.header("Step 5: Select Dispute Round")

    round_choice = st.radio(
        "What round of dispute is this?",
        ["Personal Info", "Round 1", "Round 2", "Round 3"],
        index=1,
        key="s5_round_choice"
    )
    st.session_state.dispute_round = round_choice

    # Strategy only for Round 2 / 3
    strategy = None
    if round_choice in ["Round 2", "Round 3"]:
        strat_label = st.radio(
            "Round strategy",
            ["Method of Verification (MOV)", "Factual"],
            index=0,
            key="s5_strategy"
        )
        strategy = "mov" if strat_label.startswith("Method") else "factual"
    st.session_state.round_strategy = strategy

    with st.expander("How to use the rounds (optional help)", expanded=False):
        st.markdown(
            "- **Personal Info** (pre-step): clean old addresses/names/employers first.\n"
            "- **Round 1**: friendly investigation; items are *unfamiliar*.\n"
            "- **Round 2**: choose **MOV** (how did you verify?) **or** **Factual** (specific errors like monthly charge-off updates / Metro 2 plain-language).\n"
            "- **Round 3**: send whichever you didn’t use in Round 2.\n"
            "- Don’t dispute too many accounts at once."
        )

    c1, c2 = st.columns(2)
    if c1.button("⬅️ Back"):
        st.session_state.step = 4.5
        st.rerun()
    if c2.button("Next ➡️"):
        st.session_state.step = 6
        st.rerun()
