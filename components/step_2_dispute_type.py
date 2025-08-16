import streamlit as st

def render():
    st.header("Step 2: What Are You Disputing?")

    st.markdown("Select the item(s) you'd like to dispute:")

    dispute_options = [
        "Account (charge-offs, collections, etc.)",
        "Personal Information (name, address, etc.)",
        "Hard Inquiry (unauthorized inquiries)",
        "Duplicate Account (appears more than once)",
        "Public Record (bankruptcy, lien, judgment)",
        "Reinserted Item (previously removed but returned)",
        "Mixed File (not your account or info)",
        "Repo (repossessed vehicle)",
        "Other"
    ]

    selected = st.multiselect("Dispute Categories:", dispute_options)

    if selected:
        st.session_state.dispute_types = selected

    if st.button("Next"):
        if selected:
            st.session_state.step = 3
        else:
            st.warning("Please select at least one dispute type.")
