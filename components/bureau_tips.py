# components/bureau_tips.py
import streamlit as st

BUREAU_TIPS = {
    "Equifax": [
        "Equifax address for disputes: P.O. Box 740256, Atlanta, GA 30374.",
        "Include clear facts (names, last-4 only, YYYY-MM dates).",
        "Avoid legal threats; focus on accuracy, completeness, verification."
    ],
    "Experian": [
        "Experian uses Allen, TX address for disputes.",
        "Ask for Method of Verification only if they ‘verify’.",
        "Keep identity info consistent across rounds."
    ],
    "TransUnion": [
        "TransUnion: P.O. Box 2000, Chester, PA 19016-2000.",
        "If an item was reinserted, ask whether written notice was sent within 5 business days.",
        "For charge-offs/collections, avoid ‘monthly re-aging’; keep DOFD accurate."
    ],
}

def render_for(bureau: str):
    tips = BUREAU_TIPS.get(bureau)
    if not tips: 
        return
    with st.expander(f"💡 Tips for {bureau}", expanded=True):
        for t in tips:
            st.markdown(f"- {t}")
