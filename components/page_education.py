# components/page_education.py
import streamlit as st
from utils.tips import get_contextual_tips, get_law_cards, TIP_BANK

def render():
    st.header("🎓 Tips & Education Hub")
    st.caption("Quick, practical guidance. Not legal advice.")

    # Context from current session (if available)
    # Prefer context coming from History -> "Tips for this"
    ctx = st.session_state.get("edu_context") or {}
    if ctx:
        dispute_types = ctx.get("dispute_types", [])
        round_num = ctx.get("round", "Round 1")
    else:
        dispute_types = st.session_state.get("dispute_types", [])
        round_num = st.session_state.get("dispute_round", "Round 1")
    if ctx:
            st.info(f"Context from Dispute History: **{ctx.get('label','Selected letter')}**")


    # Recommended tips (dynamic)
    with st.container(border=True):
        st.subheader("Recommended for You")
        recs = get_contextual_tips(dispute_types, round_num)
        # Optional search within recommended
        q = st.text_input("Search within tips", key="edu_search")
        if q.strip():
            recs = [t for t in recs if q.lower() in t.lower()]
        for t in recs[:50]:
            st.markdown(f"- {t}")

    st.markdown("---")

    tabs = st.tabs(["Guides", "Laws (Plain English)", "Best Practices", "FAQs"])

    with tabs[0]:
        st.subheader("Step-by-Step Guides")
        with st.expander("Preparing a Strong Round 1 Dispute"):
            st.markdown("""
1. Identify the exact line(s) to dispute and why they’re inaccurate/incomplete/unverifiable.  
2. Provide **only** supporting pages that matter (highlight the lines).  
3. Keep tone factual: request a **reasonable reinvestigation** and correction or deletion.  
4. Save tracking and create a simple timeline (sent date → response date → result).  
            """)
        with st.expander("Follow-Up (Round 2+) Without Repeating Yourself"):
            st.markdown("""
- Reference your **prior dispute date** and summarize the bureau’s response.  
- Clarify **what remains inaccurate** and why; do not paste the same letter.  
- Request **method of verification** and furnisher contact if they say “verified.”  
            """)
        with st.expander("When to Mention Metro 2"):
            st.markdown("""
- Use it to frame **accuracy expectations** (balances, dates, statuses), not to demand codes.  
- Keep it plain: ask them to ensure the tradeline matches accurate data consistently.  
            """)

    with tabs[1]:
        st.subheader("Laws (Plain English)")
        for title, bullets in get_law_cards().items():
            with st.expander(title):
                for b in bullets:
                    st.markdown(f"- {b}")

    with tabs[2]:
        st.subheader("Best Practices")
        for tip in TIP_BANK["documentation"] + TIP_BANK["mailing"] + TIP_BANK["followup"]:
            st.markdown(f"- {tip}")

    with tabs[3]:
        st.subheader("FAQs")
        with st.expander("How long does a bureau have to respond?"):
            st.write("Generally **30 days** from receipt for reinvestigation; +15 days if you supply new docs mid-investigation.")
        with st.expander("Should I send disputes online or by mail?"):
            st.write("Mail gives you tracking and a paper trail. If you dispute online, always download the response PDF.")
        with st.expander("Can I dispute multiple items at once?"):
            st.write("Yes, but keep each item specific. Overloaded letters can delay clean outcomes.")
        with st.expander("My item was deleted then came back. What now?"):
            st.write("That’s a **reinsertion** scenario—ask for when/why it was reinserted and which furnisher data was relied upon.")
        with st.expander("Do I still owe a debt if it’s deleted?"):
            st.write("Removal for accuracy/verification reasons doesn’t erase the underlying debt. You may still owe it.")

    st.markdown("---")
    cols = st.columns([1,1,2])
    with cols[0]:
        if st.button("🏠 Back to Start"):
            st.session_state.clear()
            st.session_state.step = 1
            st.session_state.pop("edu_context", None)
            st.rerun()
    with cols[1]:
        if st.button("📝 New Letter"):
            st.session_state.step = 2
            st.session_state.pop("edu_context", None)
            st.rerun()

           
