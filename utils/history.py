# utils/history.py
import os, io, re, uuid, datetime
import pandas as pd
from fpdf import FPDF

# Where we keep history + saved letters
DATA_DIR = "data"
HISTORY_PATH = os.path.join(DATA_DIR, "dispute_history.csv")
LETTERS_DIR = os.path.join(DATA_DIR, "letters")

STATUS_CHOICES = ["Prepared", "Sent", "Responded", "Resolved", "Closed"]

def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LETTERS_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_PATH):
        df = pd.DataFrame(columns=[
            "id","created_at","full_name","owner_email","bureau","round","dispute_types",
            "status","txt_path","pdf_path"
        ])
        df.to_csv(HISTORY_PATH, index=False)
    else:
        # Ensure owner_email exists in older CSVs
        df = pd.read_csv(HISTORY_PATH)
        if "owner_email" not in df.columns:
            df["owner_email"] = ""
            df.to_csv(HISTORY_PATH, index=False)

def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-") or "letter"

def save_letter_files(letter_text: str, full_name: str, bureau: str) -> tuple[str, str]:
    _ensure_dirs()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{_slugify(full_name)}-{_slugify(bureau)}-{stamp}"

    txt_path = os.path.join(LETTERS_DIR, f"{base}.txt")
    with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(letter_text)

    pdf_path = os.path.join(LETTERS_DIR, f"{base}.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for line in letter_text.split("\n"):
        try:
            pdf.multi_cell(0, 10, line.encode("latin-1", "replace").decode("latin-1"))
        except Exception:
            pdf.multi_cell(0, 10, line.encode("ascii", "ignore").decode("ascii"))
    pdf.output(pdf_path)

    return txt_path, pdf_path

def log_dispute(full_name: str,
                bureau: str,
                round_num: str,
                dispute_types: list[str],
                txt_path: str,
                pdf_path: str,
                owner_email: str | None = None):
    """
    Append a row to the history CSV.
    """
    _ensure_dirs()
    row = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "full_name": full_name,
        "owner_email": owner_email or "",
        "bureau": bureau,
        "round": str(round_num),
        "dispute_types": ", ".join([dt.replace("_"," ").title() for dt in dispute_types]) if dispute_types else "",
        "status": "Prepared",
        "txt_path": txt_path,
        "pdf_path": pdf_path,
    }
    df = pd.read_csv(HISTORY_PATH)
    for k in row.keys():
        if k not in df.columns:
            df[k] = ""
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(HISTORY_PATH, index=False)
    return row["id"]

def load_history() -> pd.DataFrame:
    _ensure_dirs()
    try:
        return pd.read_csv(HISTORY_PATH)
    except Exception:
        return pd.DataFrame(columns=[
            "id","created_at","full_name","owner_email","bureau","round",
            "dispute_types","status","txt_path","pdf_path"
        ])

def update_status(row_id: str, new_status: str) -> bool:
    _ensure_dirs()
    df = pd.read_csv(HISTORY_PATH)
    if row_id not in set(df["id"].astype(str)):
        return False
    if new_status not in STATUS_CHOICES:
        return False
    df.loc[df["id"].astype(str) == row_id, "status"] = new_status
    df.to_csv(HISTORY_PATH, index=False)
    return True
