# utils/prompt_builder.py
# Build the BODY ONLY of the dispute letter (header/signature added in Step 8)

def build_prompt(
    user_info,
    dispute_details,
    dispute_types,
    bureau,
    round_num,              # "Personal Info" or 1 / 2 / 3 (int or str)
    law_selection,
    strategy=None           # optional: "mov" or "factual" for R2/R3
):
    """
    Returns a single prompt string for the LLM.

    Modes:
      - "Personal Info"   -> Personal info cleanup (pre-step, not a round)
      - Round 1           -> Soft investigation request (consumer tone)
      - Round 2           -> MOV or Factual (choose via `strategy`)
      - Round 3           -> whichever wasn't used in Round 2 (or pass `strategy`)

    Multi-account support:
      - Step 4.5 can store a list in dispute_details["account_items"] with up to 5 items:
        {name, last4, issue, docs, dofd_ym, event_ym}
      - If present, we use those to create individual fact bullets.
      - If absent, we fall back to the older single-account fields.
    """

    # ---------- normalize round & strategy ----------
    r = str(round_num).strip().lower()
    if r in {"personal", "personal info", "personal_info"}:
        mode = "pi"
    elif r in {"1", "round 1", "round1"}:
        mode = "r1"
    elif r in {"2", "round 2", "round2"}:
        mode = "r2"
    elif r in {"3", "round 3", "round3"}:
        mode = "r3"
    else:
        mode = "r1"  # safe default

    s = (strategy or "").strip().lower()
    if mode == "r2" and s not in {"mov", "factual"}:
        s = "mov"
    if mode == "r3" and s not in {"mov", "factual"}:
        s = "factual"

    # ---------- normalize dispute types ----------
    types = []
    if isinstance(dispute_types, (list, tuple)):
        for t in dispute_types:
            types.append(str(t).lower().replace(" ", "_"))
    elif dispute_types:
        types.append(str(dispute_types).lower().replace(" ", "_"))
    dtype_anchor = types[0] if types else ""
    dd = dispute_details or {}

    # ---------- derive concise fact bullets ----------
    fact_lines = []
    # flags for specialized guidance
    involves_collections = False
    mentions_monthly_chargeoff = False
    mentions_monthly_collection = False
    mentions_past_due_after_co = False
    involves_repo = False
    involves_reinsertion = False
    involves_inquiry = False
    involves_duplicate = False
    involves_mixed_file = False
    involves_public_record = False

    reinsertion_notice_claim = None  # "no_notice" / "unknown"

    # Prefer list-based multi-account if present
    account_items = dd.get("account_items")
    if isinstance(account_items, list) and account_items:
        for it in account_items[:5]:
            nm    = (it.get("name") or "").strip()
            issue = (it.get("issue") or "").strip()
            last4 = (it.get("last4") or "").strip()
            docs  = (it.get("docs") or "").strip()
            dofd  = (it.get("dofd_ym") or "").strip()
            event = (it.get("event_ym") or "").strip()

            extras = []
            if dofd:  extras.append(f"DOFD approx: {dofd}")
            if event: extras.append(f"Event month: {event}")
            extra_str = f"; {'; '.join(extras)}" if extras else ""

            fact_lines.append(
                f"Account — Furnisher: {nm or 'Unknown'}; Last4: {last4 or 'N/A'}; Issue: {issue or 'N/A'}{extra_str}; Docs: {docs or 'N/A'}"
            )

            hay_issue = issue.lower()
            if "collection" in hay_issue:
                involves_collections = True
                if any(p in hay_issue for p in ["every month", "each month", "monthly", "re-aging", "reaging", "re aged", "reaged"]):
                    mentions_monthly_collection = True
            if any(p in hay_issue for p in [
                "charge off every month", "monthly charge-off", "charged off each month",
                "every month", "each month", "monthly", "re-aging", "reaging", "re aged", "reaged"
            ]):
                mentions_monthly_chargeoff = True
            if "past due" in hay_issue and ("co" in hay_issue or "charge-off" in hay_issue or "charge off" in hay_issue):
                mentions_past_due_after_co = True

        types_wo_account = [t for t in types if t != "account"]
    else:
        types_wo_account = types

    # Handle other single-type facts
    for dtype in types_wo_account or [dtype_anchor or ""]:
        if not dtype:
            continue
        info = dd.get(dtype, {}) if isinstance(dd.get(dtype, {}), dict) else dd
        low_issue = ((info.get("issue") or "") + " " + (info.get("details") or "")).lower()

        if dtype == "account":
            nm    = (info.get("name") or "").strip()
            issue = (info.get("issue") or "").strip()
            last4 = (info.get("last4") or info.get("account_number") or "").strip()
            docs  = (info.get("docs") or info.get("documentation") or "").strip()
            fact_lines.append(
                f"Account — Furnisher: {nm or 'Unknown'}; Last4: {last4 or 'N/A'}; Issue: {issue or 'N/A'}; Docs: {docs or 'N/A'}"
            )
            if "collection" in low_issue:
                involves_collections = True
            if any(p in low_issue for p in [
                "charge off every month", "monthly charge-off", "charged off each month",
                "every month", "each month", "monthly", "re-aging", "reaging", "re aged", "reaged"
            ]):
                mentions_monthly_chargeoff = True
            if "past due" in low_issue and ("co" in low_issue or "charge-off" in low_issue or "charge off" in low_issue):
                mentions_past_due_after_co = True

        elif dtype in {"collection"}:
            nm    = (info.get("name") or "").strip()
            issue = (info.get("issue") or "").strip()
            last4 = (info.get("last4") or "").strip()
            fact_lines.append(
                f"Collection — Agency: {nm or 'Unknown'}; Last4: {last4 or 'N/A'}; Issue: {issue or 'N/A'}"
            )
            involves_collections = True
            if any(p in issue.lower() for p in ["every month", "each month", "monthly", "re-aging", "reaging", "re aged", "reaged"]):
                mentions_monthly_collection = True

        elif dtype in {"inquiry", "hard_inquiry"}:
            involves_inquiry = True
            nm = (info.get("name") or "").strip()
            reason = (info.get("reason") or "").strip()
            fact_lines.append(
                f"Hard inquiry — Creditor: {nm or 'Unknown'}; Reason unauthorized: {reason or 'N/A'}"
            )

        elif dtype in {"personal_info", "personal_information"}:
            fact_lines.append(
                f"Personal info — Incorrect: {info.get('wrong','') or 'N/A'}; Should be: {info.get('correct','') or 'N/A'}"
            )

        elif dtype == "public_record":
            involves_public_record = True
            fact_lines.append(
                f"Public record — Type: {info.get('type','') or 'Unknown'}; Issue: {info.get('issue','') or 'N/A'}"
            )

        elif dtype == "duplicate":
            involves_duplicate = True
            nm = (info.get("name","") or "").strip()
            details = (info.get("details","") or "").strip()
            fact_lines.append(
                f"Duplicate tradeline — Name: {nm or 'Unknown'}; Why duplicate: {details or 'N/A'}"
            )

        elif dtype == "repo":
            involves_repo = True
            fact_lines.append(
                f"Repossession reporting — Type: {info.get('type','') or 'Unknown'}; Issue: {info.get('issue','') or 'N/A'}"
            )

        elif dtype == "mixed_file":
            involves_mixed_file = True
            fact_lines.append(
                f"Mixed file — Not mine / incorrect info present: {info.get('issue','') or 'N/A'}"
            )

        elif dtype == "reinserted":
            involves_reinsertion = True
            details = (info.get('details','') or '').strip()
            fact_lines.append(
                f"Reinserted item — Details: {details or 'N/A'}"
            )
            low = details.lower()
            if any(kw in low for kw in ["no notice", "did not receive", "never received", "no letter", "no written notice"]):
                reinsertion_notice_claim = "no_notice"
            else:
                reinsertion_notice_claim = reinsertion_notice_claim or "unknown"

        elif dtype == "other":
            fact_lines.append(
                f"Other — Details: {info.get('details','') or 'N/A'}"
            )

    # If NOT in Personal Info mode, prevent PI bullets from hijacking the letter.
    if mode != "pi":
        fact_lines = [ln for ln in fact_lines if not ln.lower().startswith("personal info")]

    # Fallback anchor if nothing present
    if not fact_lines:
        if dtype_anchor == "account":
            fact_lines.append("Account — Details not provided; focus on accuracy, completeness, and verification.")
        elif dtype_anchor in {"collection"}:
            fact_lines.append("Collection — Details not provided; focus on accuracy, completeness, and verification.")
        else:
            fact_lines.append("General dispute — Focus on accurate, complete, and verifiable reporting.")

    # ---------- law references ----------
    def legal_laws_text():
        if law_selection:
            return ", ".join(law_selection)
        laws = ["FCRA §611 (reinvestigation)", "FCRA §602 (accuracy)"]
        # furnishers duties for tradelines/collections/repo/duplicate
        if any(dt in ["account", "duplicate", "repo", "collection"]
               for dt in [d.lower().replace(" ", "_") for d in (dispute_types or [])]):
            laws.append("FCRA §623 / 15 USC 1681s-2 (duties of furnishers)")
        # reinsertion notice rule
        if involves_reinsertion:
            laws.append("FCRA §611(a)(5)(B) (reinsertion notice within 5 business days)")
        # inquiries permissible purpose
        if involves_inquiry:
            laws.append("FCRA §604 (permissible purpose for inquiries)")
        # DOFD / obsolescence context
        if mentions_monthly_chargeoff or mentions_monthly_collection or mentions_past_due_after_co:
            laws.append("FCRA §623(a)(5) (accurate DOFD reporting)")
            laws.append("FCRA §605(c) (obsolescence period measured from DOFD)")
        return ", ".join(laws)

    # ---------- optional guidance / hints (plain-English) ----------
    extra_hints = []

    # Monthly CO / collection pattern (re-aging / repeated derogs)
    if mentions_monthly_chargeoff or mentions_monthly_collection:
        extra_hints.append(
            "Treat a charge-off or collection as a single historical event; do not make it appear newly derogatory each month, and do not advance the Date of First Delinquency (no re-aging)."
        )

    # Past-due showing after CO
    if mentions_past_due_after_co:
        extra_hints.append(
            "After a charge-off, the 'past due' field generally should not continue to accrue as new past-due amounts. If the debt was sold/transferred, the original creditor typically shows a $0 balance."
        )

    # Repo-specific guidance
    if involves_repo:
        extra_hints.append(
            "For repossessions, ensure accurate sale date, proceeds/credits, any deficiency balance, and consistent remarks; do not duplicate balances between original creditor and any collector; do not move the DOFD forward."
        )

    # Collections general
    if involves_collections:
        extra_hints.append(
            "If a debt collector is involved, they must report accurately and stop reporting information that cannot be substantiated."
        )

    # Reinsertion general
    if involves_reinsertion:
        if reinsertion_notice_claim == "no_notice":
            extra_hints.append(
                "State that no written reinsertion notice was received within 5 business days and request deletion until proper verification and notice are provided."
            )
        else:
            extra_hints.append(
                "Ask the bureau to confirm whether written notice of reinsertion was sent within 5 business days and, if not, to delete the item until proper verification is completed."
            )

    # Inquiries general
    if involves_inquiry:
        extra_hints.append(
            "Ask for the specific permissible purpose or a copy of the signed authorization for the inquiry; if none exists, request deletion of the inquiry."
        )

    # Duplicate tradeline
    if involves_duplicate:
        extra_hints.append(
            "Request deletion of the duplicate tradeline so that only a single, accurate account remains; avoid double counting of balances or payment history."
        )

    # Mixed file
    if involves_mixed_file:
        extra_hints.append(
            "Request removal of any data that does not belong to the consumer and confirmation of the data sources used to associate those records."
        )

    # Public record
    if involves_public_record:
        extra_hints.append(
            "Ask the bureau to identify the public record source it relied upon and to delete the item if it cannot be verified for accuracy and completeness."
        )

    # Keep “industry standards” wording generic
    extra_hints.append(
        "Ensure status/balance/remark fields follow recognized industry reporting standards and are consistent across all versions of the file."
    )

    # ---------- voice & requests by mode ----------
    if mode == "pi":
        voice = """Voice & tone:
- First-person consumer. Friendly, brief, and factual.
- Focus ONLY on personal information (addresses, names, employers). No account disputes here."""
        requests = """Requests to include:
- Remove outdated or incorrect personal information listed in the facts below.
- Ensure my file reflects only current, accurate personal information.
- Apply changes across all versions of my file and send me an updated report."""
        laws_text = "federal credit reporting law that requires accurate and up-to-date personal information"
        word_range = "120–200"

    elif mode == "r1":
        voice = """Voice & tone:
- First-person consumer. Friendly but firm. Plain English—no legalese.
- Do NOT deny ownership unless identity theft was indicated. Use 'unfamiliar' / 'do not recognize' phrasing."""
        base_requests = [
            "Conduct a reasonable reinvestigation within the normal timeline.",
            "If any item cannot be fully verified as accurate and complete, delete it or correct it across all versions of my file.",
            "If verified, provide the method of verification and the furnisher’s contact details (name, address, phone).",
            "Send me an updated copy of my report reflecting any changes.",
        ]
        # targeted adds
        if involves_reinsertion:
            base_requests.insert(0, "Confirm whether written reinsertion notice was sent within 5 business days as required by FCRA §611(a)(5)(B).")
            base_requests.insert(1, "If the notice was not sent or the reinsertion cannot be substantiated, delete the item until proper verification is completed.")
        if involves_inquiry:
            base_requests.insert(0, "Identify the specific permissible purpose or provide a copy of the signed authorization for the inquiry; delete it if neither exists (FCRA §604).")
        if mentions_monthly_chargeoff or mentions_monthly_collection:
            base_requests.append("Correct reporting so the item reflects a single historical event and does not appear newly derogatory each month (no re-aging; accurate DOFD).")
        if mentions_past_due_after_co:
            base_requests.append("Correct any 'past due' amounts reported after a charge-off where no new past-due should accrue.")
        if involves_repo:
            base_requests.append("Confirm sale date, proceeds/credits, any deficiency balance, and ensure no duplicate balances between original creditor and any collector.")
        if involves_duplicate:
            base_requests.append("Delete the duplicate tradeline so only one accurate account remains.")
        if involves_mixed_file:
            base_requests.append("Remove data that does not belong to me and confirm the data sources used to associate those records.")
        if involves_public_record:
            base_requests.append("Identify the public record source relied upon and delete the item if it cannot be verified.")
        requests = "Requests to include:\n- " + "\n- ".join(base_requests)
        laws_text = "federal credit reporting law that requires accurate, complete, and verifiable reporting"
        word_range = "140–220"

    elif mode == "r2":
        if s == "mov":
            voice = """Voice & tone:
- First-person consumer. Direct but polite. Plain English.
- Focus on how the item was verified; avoid legal jargon."""
            base_requests = [
                "Provide the specific method of verification.",
                "Provide the name, address, and phone number of the furnisher relied upon.",
                "If you cannot fully verify accuracy and completeness, delete or correct the item across all versions of my file.",
                "Send me an updated report reflecting the outcome.",
            ]
            if involves_reinsertion:
                base_requests.insert(0, "Confirm whether written reinsertion notice was sent within 5 business days (FCRA §611(a)(5)(B)); if not, delete the item until proper verification is completed.")
            if involves_inquiry:
                base_requests.insert(0, "Provide the permissible purpose or signed authorization for the inquiry; delete if neither exists (FCRA §604).")
            if mentions_monthly_chargeoff or mentions_monthly_collection:
                base_requests.append("Affirm that reporting will not re-age the item or make it appear newly derogatory each month; ensure the DOFD is accurate.")
            if mentions_past_due_after_co:
                base_requests.append("Correct any 'past due' reporting that continues after a charge-off where no new past-due should accrue.")
            if involves_repo:
                base_requests.append("Confirm sale date, proceeds/credits, any deficiency balance, and remove any duplicate balances across furnishers.")
            if involves_duplicate:
                base_requests.append("Remove the duplicate tradeline and ensure balances/payment history are not double-counted.")
            if involves_mixed_file:
                base_requests.append("Remove records that do not belong to me and confirm the data sources used.")
            if involves_public_record:
                base_requests.append("Identify the public record source and delete the item if it cannot be verified.")
            requests = "Requests to include:\n- " + "\n- ".join(base_requests)
            laws_text = "my right to a reasonable reinvestigation and to understand how items are verified"
            word_range = "140–220"
        else:  # factual
            voice = """Voice & tone:
- Clear, consumer-friendly, and factual. Prefer 'appears inconsistent with' rather than legalistic conclusions.
- Keep the focus on correcting or deleting inaccuracies and requesting MOV details only if the item is verified."""
            base_requests = [
                "Correct the specific inaccuracies (status/balance/remarks/DOFD) so the item reflects a single historical event where applicable, or delete it if it cannot be fully verified as accurate and complete.",
                "If verified, provide the method of verification and the furnisher’s name, address, and phone number.",
                "Apply corrections across all versions of my file and send an updated copy of my report.",
            ]
            if involves_reinsertion:
                base_requests.insert(0, "Confirm whether written reinsertion notice was sent within 5 business days (FCRA §611(a)(5)(B)); if not, delete the item until proper verification is completed.")
            if involves_inquiry:
                base_requests.insert(0, "Identify the permissible purpose or provide signed authorization for the inquiry; delete if neither exists (FCRA §604).")
            if mentions_monthly_chargeoff or mentions_monthly_collection:
                base_requests.append("Ensure the item does not re-age or appear newly derogatory each month; keep DOFD accurate.")
            if mentions_past_due_after_co:
                base_requests.append("Remove any 'past due' amounts that continue post charge-off where they should not accrue.")
            if involves_repo:
                base_requests.append("Report sale date, proceeds/credits, any deficiency, and avoid duplicate balances between original creditor and collector.")
            if involves_duplicate:
                base_requests.append("Delete the duplicate tradeline; keep one accurate account only.")
            if involves_mixed_file:
                base_requests.append("Remove non-belonging records and confirm source matching used.")
            if involves_public_record:
                base_requests.append("Identify the public record source; delete the item if it cannot be verified.")
            requests = "Requests to include:\n- " + "\n- ".join(base_requests)
            laws_text = legal_laws_text()
            word_range = "180–300"

    else:  # mode == "r3"
        if s == "mov":
            voice = """Voice & tone:
- Firm but professional. Focus on verification process and transparency."""
            base_requests = [
                "Provide the exact method of verification and furnisher contact details used in your prior decision.",
                "If prior verification cannot be substantiated, delete or correct the item immediately and confirm in writing.",
                "Send me an updated report reflecting the final disposition.",
            ]
            if involves_reinsertion:
                base_requests.insert(0, "Confirm whether written reinsertion notice was sent within 5 business days (FCRA §611(a)(5)(B)); if not, delete the item until proper verification is completed.")
            if involves_inquiry:
                base_requests.insert(0, "Provide the permissible purpose or signed authorization for the inquiry; delete if neither exists (FCRA §604).")
            if mentions_monthly_chargeoff or mentions_monthly_collection:
                base_requests.append("Affirm that reporting will not re-age or appear newly derogatory each month; DOFD must remain accurate.")
            if mentions_past_due_after_co:
                base_requests.append("Correct any 'past due' accrual shown after a charge-off where inappropriate.")
            if involves_repo:
                base_requests.append("Confirm sale date, proceeds/credits, any deficiency, and remove duplicates across furnishers.")
            if involves_duplicate:
                base_requests.append("Delete duplicate tradeline(s) so that only one accurate account remains.")
            if involves_mixed_file:
                base_requests.append("Remove non-belonging records and confirm matching logic.")
            if involves_public_record:
                base_requests.append("Identify the public record source; delete the item if unverifiable.")
            requests = "Requests to include:\n- " + "\n- ".join(base_requests)
            laws_text = "my right to a reasonable reinvestigation and to understand how items are verified"
            word_range = "150–240"
        else:  # factual
            voice = """Voice & tone:
- Firm, factual, professional. Prefer 'appears inconsistent with' to avoid overreach. Keep requests specific and actionable."""
            base_requests = [
                "Correct or delete the specific inaccuracies listed below and stop any practice that makes the item appear newly derogatory each month. Do not advance the original delinquency date (no re-aging).",
                "If verified, provide method of verification and furnisher contact; apply corrections across all file versions and send an updated report.",
            ]
            if involves_reinsertion:
                base_requests.insert(0, "Confirm whether written reinsertion notice was sent within 5 business days (FCRA §611(a)(5)(B)); if not, delete the item until proper verification is completed.")
            if involves_inquiry:
                base_requests.insert(0, "Identify the permissible purpose or provide signed authorization for the inquiry; delete if neither exists (FCRA §604).")
            if mentions_monthly_chargeoff or mentions_monthly_collection:
                base_requests.append("Ensure the item reflects a single historical event and does not re-age; keep DOFD accurate.")
            if mentions_past_due_after_co:
                base_requests.append("Remove any inappropriate 'past due' amounts shown after a charge-off.")
            if involves_repo:
                base_requests.append("Report sale date, proceeds/credits, any deficiency; avoid duplicate balances between original creditor and collector.")
            if involves_duplicate:
                base_requests.append("Delete duplicate tradeline entries and maintain one accurate account.")
            if involves_mixed_file:
                base_requests.append("Remove data that does not belong to me and confirm the source matching used.")
            if involves_public_record:
                base_requests.append("Identify the public record source relied upon; delete if unverifiable.")
            requests = "Requests to include:\n- " + "\n- ".join(base_requests)
            laws_text = legal_laws_text()
            word_range = "180–320"

    # ---------- assemble final prompt ----------
    facts_block = "- " + "\n- ".join(fact_lines) if fact_lines else "- (No facts were provided.)"

    hints_block = ""
    if extra_hints:
        hints_block = "- " + "\n- ".join(extra_hints)

    purpose = (
        "Personal info cleanup" if mode == "pi" else
        ("Round 1 investigation" if mode == "r1" else
         ("Round 2 – " + s.upper() if mode == "r2" else "Round 3 – " + s.upper()))
    )

    prompt = f"""
Write ONLY the body paragraphs of a consumer credit letter.
Do NOT include the consumer header, bureau address, date, salutation, or signature.

Voice & tone and style guidance:
{voice}

Context:
- Purpose: {purpose}
- Bureau: {bureau}
- Laws to consider: {laws_text}

Facts to address (use only what is relevant; do not invent details):
{facts_block}

Requests:
{requests}

Style constraints:
- {word_range} words in 2–5 short paragraphs.
- Use unique phrasing (avoid boilerplate like "I am writing to dispute..."; vary the first sentence).
- Be specific about the remedy (delete, correct, or cease reporting).
{("Additional considerations:\n" + hints_block) if hints_block else ""}
""".strip()

    return prompt
