def build_prompt(user_info, dispute_details, dispute_types, bureau, round_num, law_selection):
    """
    Return ONLY the BODY paragraphs of the dispute letter.
    (No consumer header, no bureau address, no date, no 'Dear ...', no signature.)
    Step 8 is responsible for all framing around the body.
    """

    # --------- derive concise fact bullets the model can use ----------
    fact_lines = []
    involves_collections = False

    for dtype in dispute_types:
        key = dtype.lower().replace(" ", "_")
        info = dispute_details.get(key, {}) or {}

        if key == "account":
            nm = info.get("name", "") or ""
            issue = info.get("issue", "") or ""
            last4 = info.get("last4", "") or ""
            docs = info.get("docs", "") or ""
            fact_lines.append(
                f"Account dispute — Furnisher: {nm}; Last4: {last4}; Issue: {issue}; Docs: {docs}"
            )
            if "collection" in (nm + " " + issue).lower():
                involves_collections = True

        elif key == "inquiry":
            fact_lines.append(
                f"Hard inquiry dispute — Creditor: {info.get('name','')}; Reason unauthorized: {info.get('reason','')}"
            )

        elif key == "personal_info":
            fact_lines.append(
                f"Personal info dispute — Incorrect: {info.get('wrong','')}; Should be: {info.get('correct','')}"
            )

        elif key == "public_record":
            fact_lines.append(
                f"Public record dispute — Type: {info.get('type','')}; Issue: {info.get('issue','')}"
            )

        elif key == "duplicate":
            nm = info.get("name","") or ""
            details = info.get("details","") or ""
            fact_lines.append(
                f"Duplicate account dispute — Name: {nm}; Why duplicate: {details}"
            )
            if "collection" in (nm + " " + details).lower():
                involves_collections = True

        elif key == "repo":
            fact_lines.append(
                f"Repossession reporting dispute — Type: {info.get('type','')}; Issue: {info.get('issue','')}"
            )

        elif key == "mixed_file":
            fact_lines.append(
                f"Mixed file dispute — Not mine / incorrect info present: {info.get('issue','')}"
            )

        elif key == "reinserted":
            fact_lines.append(
                f"Reinserted item dispute — Details: {info.get('details','')}"
            )

        elif key == "other":
            fact_lines.append(
                f"Other dispute — Details: {info.get('details','')}"
            )

    # Which laws to reference (if user didn’t pick any)
    if law_selection:
        laws_text = ", ".join(law_selection)
    else:
        # sensible defaults that the model can pull from
        laws = ["FCRA §611 (reinvestigation)", "FCRA §602 (accuracy)"]
        # duties of furnishers fit many account/duplicate/repo cases
        if any(dt in ["account", "duplicate", "repo"] for dt in [d.lower().replace(" ", "_") for d in dispute_types]):
            laws.append("FCRA §623 / 15 USC 1681s-2 (duties of furnishers)")
        # mixed file / personal info often leans on §611/§602 already
        laws_text = ", ".join(laws)

    # If collections are involved, allow the model to briefly layer FDCPA
    fdcpahint = "If a collection agency or debt collector is implicated, briefly note FDCPA duties (no legalese, one short sentence)." if involves_collections else ""

    # Metro 2 generally relevant to accuracy/formatting disputes
    metro2hint = ("If the issue implicates data format/accuracy (e.g., balances, statuses, duplicate tradelines, mixed file), "
                  "reference Metro 2 accuracy expectations in plain language.") 

    # --------- BODY-ONLY instructions to the model ----------
    prompt = f"""
Write ONLY the body paragraphs of a consumer credit dispute letter. 
Do NOT include the consumer header, bureau address, date, salutation, or signature — those are added elsewhere.

Voice & tone:
- First-person consumer. Clear, firm, factual, non-template. No boilerplate.
- Explain how the facts violate accuracy/completeness/verification duties under the FCRA (and furnishers' duties where relevant).
- Cite sections by purpose (e.g., FCRA §611 reinvestigation) without dumping statute text.

Context:
- Bureau: {bureau}
- Dispute round: {round_num}
- Laws to consider: {laws_text}

Facts to address (use only what is relevant; do not invent details):
- """ + "\n- ".join(fact_lines) + f"""

Requests to include:
- Conduct a reasonable reinvestigation within the statutory timeline.
- If the item cannot be fully verified as accurate and complete, delete it or correct it across all consumer file versions.
- If you verify, provide the method of verification and the name/address/phone of the furnisher relied upon.
- Require furnishers to cease reporting information that cannot be substantiated.

Style constraints:
- 180–350 words, 2–5 short paragraphs.
- Unique phrasing (avoid generic openings like "I am writing to dispute..."; vary the first sentence).
- Be specific about the relief requested (delete, correct, or cease reporting).
- {metro2hint}
- {fdcpahint}
"""
    return prompt.strip()
