# utils/tips.py

from typing import List

# Short, practical, non-legal-advice tips. Keep each item concise.
TIP_BANK = {
    "general": [
        "Keep copies of every dispute letter, report, and response in one folder.",
        "Send disputes by mail with tracking so you have a receipt and date.",
        "Only dispute facts you believe are inaccurate, incomplete, unverifiable or outdated.",
        "Update addresses and name variants first; mixed files often start there.",
        "If a bureau responds online, download and save the PDF immediately.",
    ],
    "timeline": [
        "Bureaus generally have 30 days to complete reinvestigation under FCRA §611.",
        "If you send new docs mid-investigation, the timeline can extend by up to 15 days.",
        "Keep a simple timeline: Sent date, tracking number, response date, outcome.",
    ],
    "mailing": [
        "Use the bureau’s official dispute address. Keep your return address clear and consistent.",
        "Do not mail original IDs—send clear copies with any sensitive numbers masked if appropriate.",
        "Avoid sending USBs or discs; paper is usually processed faster.",
    ],
    "documentation": [
        "Circle or highlight the specific line(s) on your report you’re disputing.",
        "Include only supporting pages that matter; avoid 50+ page bundles.",
        "If you have an identity theft report or police report, reference it plainly.",
    ],
    "followup": [
        "If the result says 'verified', request the method of verification and furnisher contact details.",
        "If a deleted item is reinserted, FCRA requires certain notifications—raise that in a follow-up.",
        "Use round 2 to clarify facts, not to repeat the same letter. Add specifics.",
    ],
    # Dispute-type specific
    "account": [
        "Ask the bureau to obtain the furnisher’s reporting data (balance, dates, status) for accuracy.",
        "If the balance/DOFD looks off, mention Metro 2 accuracy expectations in plain language.",
    ],
    "inquiry": [
        "Unauthorized hard inquiries: request the name/address/phone and method of verification.",
        "If it relates to a dealer/aggregator, note you didn’t authorize multiple hard pulls.",
    ],
    "personal_info": [
        "List each wrong item (name variant, address, employer) and provide the correct item next to it.",
        "If a wrong address created a mixed file, say that plainly and ask for purge/correction.",
    ],
    "public_record": [
        "Public records often come via third-party vendors—ask for exact source and match logic.",
        "If it’s not yours, request suppression and correction across all file versions.",
    ],
    "duplicate": [
        "Explain why entries are duplicates (same account, same balance) and request one remain, one be removed.",
        "Cite accuracy/completeness; duplicates can unfairly inflate utilization/history.",
    ],
    "repo": [
        "Repos must reflect correct dates, balance after sale, and status; ask for supporting data if misreported.",
        "If the repo was voluntary, note that status must be reported accurately.",
    ],
    "mixed_file": [
        "List the not-yours items, plus any name/address variants that caused the mix.",
        "Request a purge/segmentation of data not belonging to you.",
    ],
    "reinserted": [
        "If an item returns after deletion, reference reinsertion notice requirements under §611.",
        "Ask when/why it was reinserted and which furnisher data was relied upon.",
    ],
    # Laws (plain English summaries)
    "law_fcra_611": [
        "FCRA §611 gives you the right to dispute and requires a reasonable reinvestigation.",
        "If not verified as accurate and complete, the item must be corrected or deleted.",
    ],
    "law_fcra_609": [
        "FCRA §609 lets you request the information in your file; use when you need source details.",
    ],
    "law_fcra_623": [
        "FCRA §623 sets duties for furnishers—if they can’t substantiate, they should stop reporting.",
    ],
    "law_fdCPA": [
        "FDCPA restricts debt collector behavior; if a collector is involved, request validation details.",
    ],
    "metro2": [
        "Metro 2 is an industry format; you can reference accuracy expectations (don’t demand a specific code).",
        "Use it to support clarity about balances, dates, and status consistency across entries.",
    ],
}

def _norm_dispute_type(dt: str) -> str:
    return dt.lower().replace(" ", "_")

def get_contextual_tips(dispute_types: List[str], round_num: str) -> list[str]:
    tips = []
    # General + timeline are always helpful
    tips += TIP_BANK["general"] + TIP_BANK["timeline"]

    # Round-specific flavor
    if str(round_num).strip().lower() in ["round 1", "1", "1st", "first"]:
        tips.append("Round 1: Keep it simple and factual; point out inaccuracies and request reinvestigation.")
    else:
        tips.append("Follow-up round: Reference prior dispute date and response; clarify unresolved inaccuracies.")

    # Type-specific
    for dt in dispute_types or []:
        key = _norm_dispute_type(dt)
        if key in TIP_BANK:
            tips += TIP_BANK[key]

    # Always include best practices
    tips += TIP_BANK["mailing"] + TIP_BANK["documentation"] + TIP_BANK["followup"]
    return tips

def get_law_cards() -> dict:
    return {
        "FCRA §611 (Disputes/Reinvestigation)": TIP_BANK["law_fcra_611"],
        "FCRA §609 (File Disclosure)": TIP_BANK["law_fcra_609"],
        "FCRA §623 (Furnisher Duties)": TIP_BANK["law_fcra_623"],
        "FDCPA (Debt Collectors)": TIP_BANK["law_fdCPA"],
        "Metro 2 (Industry Format)": TIP_BANK["metro2"],
    }
# --- history → tips context helpers ---

def parse_types_from_history(dispute_types_str: str) -> list[str]:
    """
    History stores a display string like: "Account, Inquiry".
    Normalize back to our internal keys (lowercase with underscores).
    """
    if not dispute_types_str:
        return []
    parts = [p.strip() for p in dispute_types_str.split(",") if p.strip()]
    return [p.lower().replace(" ", "_") for p in parts]

def tips_from_history_row(row: dict) -> dict:
    """
    Convert a history row to a context dict for the Education Hub.
    Returns: {"dispute_types": [...], "round": "Round X", "label": "..."}
    """
    dtypes = parse_types_from_history(row.get("dispute_types", ""))
    rnd = str(row.get("round", "Round 1"))
    label = f"{row.get('full_name','')} • {row.get('bureau','')} • {rnd}"
    return {"dispute_types": dtypes, "round": rnd, "label": label}

