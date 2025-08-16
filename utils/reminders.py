# utils/reminders.py
import os, json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()
JOBS_SHEET_ID = os.getenv("JOBS_SHEET_ID")
GA_CRED_PATH  = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

LOCAL_TZ = ZoneInfo("America/New_York")

REM_HEADERS = [
    "reminder_id","letter_id","email","phone","channel","topic",
    "due_at_utc","status","payload_json","sent_at_utc","created_at_utc","updated_at_utc"
]

def _gc():
    if GA_CRED_PATH and os.path.exists(GA_CRED_PATH):
        creds = Credentials.from_service_account_file(GA_CRED_PATH, scopes=SCOPE)
        return gspread.authorize(creds)
    return gspread.service_account()

def _open_reminders_ws():
    gc = _gc()
    ss = gc.open_by_key(JOBS_SHEET_ID)
    try:
        ws = ss.worksheet("Reminders")
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet("Reminders", rows=2000, cols=len(REM_HEADERS))
        ws.append_row(REM_HEADERS)
    # Ensure header present
    headers = ws.row_values(1)
    if headers != REM_HEADERS:
        ws.clear()
        ws.append_row(REM_HEADERS)
    return ws

def _now_utc():
    return datetime.now(timezone.utc)

def schedule_followups(letter_id: str, email: str, bureau: str, round_name: str, phone: str | None = None):
    """
    Drop a series of reminders appropriate for the round. Times are UTC.
    Example cadence (you can tweak):
      - D+2: Mail your letter? (nudge)
      - D+15: Any response? If verified, request MOV.
      - D+35: Ready for next round guidance.
    """
    ws = _open_reminders_ws()
    base = _now_utc()
    plan = [
        ("mail_nudge",       base + timedelta(days=2)),
        ("status_check",     base + timedelta(days=15)),
        ("next_round_ready", base + timedelta(days=35)),
    ]
    for topic, due_at in plan:
        rem = [
            f"{letter_id}-{topic}",
            letter_id,
            email,
            phone or "",
            "email",  # default channel; you can add "sms" too
            topic,
            due_at.strftime("%Y-%m-%d %H:%M:%S"),
            "pending",
            json.dumps({"bureau": bureau, "round": round_name}, ensure_ascii=False),
            "",  # sent_at_utc
            _now_utc().strftime("%Y-%m-%d %H:%M:%S"),
            _now_utc().strftime("%Y-%m-%d %H:%M:%S"),
        ]
        ws.append_row(rem, value_input_option="USER_ENTERED")

def list_due_reminders(limit: int = 50):
    """Return pending reminders due now or earlier."""
    ws = _open_reminders_ws()
    rows = ws.get_all_values()
    hdr = rows[0] if rows else []
    idx = {h:i for i,h in enumerate(hdr)}
    out = []
    now = _now_utc()
    for r in rows[1:]:
        try:
            status = r[idx["status"]].strip().lower()
            due = r[idx["due_at_utc"]].strip()
            if status != "pending" or not due:
                continue
            due_dt = datetime.strptime(due, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if due_dt <= now:
                out.append({
                    "reminder_id": r[idx["reminder_id"]],
                    "letter_id": r[idx["letter_id"]],
                    "email": r[idx["email"]],
                    "phone": r[idx["phone"]],
                    "channel": r[idx["channel"]],
                    "topic": r[idx["topic"]],
                    "payload": json.loads(r[idx["payload_json"]] or "{}"),
                    "__row": len(out) + 2  # not exact row; we’ll update by A1 later
                })
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out

def mark_sent(reminder_id: str, sent_ok: bool):
    ws = _open_reminders_ws()
    rows = ws.get_all_values()
    hdr = rows[0]
    idx = {h:i for i,h in enumerate(hdr)}
    for i, r in enumerate(rows[1:], start=2):
        if r and r[0] == reminder_id:
            ws.update_cell(i, idx["status"]+1, "sent" if sent_ok else "failed")
            ws.update_cell(i, idx["sent_at_utc"]+1, _now_utc().strftime("%Y-%m-%d %H:%M:%S"))
            ws.update_cell(i, idx["updated_at_utc"]+1, _now_utc().strftime("%Y-%m-%d %H:%M:%S"))
            return
