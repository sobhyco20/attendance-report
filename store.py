# =========================
# store.py — طبقة البيانات الموحّدة
#   Supabase (حفظ دائم) لو مضبوط في Secrets، وإلا ملفات Excel محلية (حفظ مؤقت).
#   كل الشاشات بتتعامل مع الدوال دي بس، من غير ما تعرف البيانات محفوظة فين.
# =========================
import os

import pandas as pd
import streamlit as st

import supabase_store as sb
from core import (
    EMP_PATH, LEAVES_PATH, ABSENCES_PATH, ATTACHMENTS_DIR,
    fmt_id, safe_str, sanitize_filename,
)

KINDS = {
    "leaves":   {"table": "leaves",   "key": "leave_id",  "prefix": "LV", "cols": sb.LEAVE_COLS, "path": LEAVES_PATH},
    "absences": {"table": "absences", "key": "record_id", "prefix": "AB", "cols": sb.ABS_COLS,   "path": ABSENCES_PATH},
}
DATE_COLS = ("start_date", "end_date")


# -------------------------------------------------
# حالة الاتصال
# -------------------------------------------------
def is_cloud() -> bool:
    return sb.is_enabled()


@st.cache_data(ttl=120, show_spinner=False)
def _status_cached(_marker: str):
    return sb.connection_status()


def status() -> tuple[bool, str]:
    if not sb.is_enabled():
        ok, msg = sb.connection_status()
        return False, msg
    url, _ = sb._cfg()
    return _status_cached(url)


# -------------------------------------------------
# القراءة (مع كاش قصير — بيتمسح فورًا بعد أي حفظ)
# -------------------------------------------------
def _normalize(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    df = df.copy() if df is not None else pd.DataFrame()
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols].copy()
    for c in cols:
        if c in DATE_COLS:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.normalize()
        elif c == "created_at":
            df[c] = pd.to_datetime(df[c], errors="coerce")
        elif c in ("employee_id", "employee_no"):
            df[c] = df[c].apply(fmt_id)
        else:
            df[c] = df[c].apply(safe_str)
    df = df[df["employee_id"] != ""]
    return df.reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def _load_cached(kind: str, cloud: bool) -> pd.DataFrame:
    k = KINDS[kind]
    if cloud:
        raw = sb.read_leaves() if kind == "leaves" else sb.read_absences()
    else:
        raw = pd.read_excel(k["path"]) if os.path.exists(k["path"]) else pd.DataFrame()
    return _normalize(raw, k["cols"])


def load(kind: str) -> pd.DataFrame:
    try:
        return _load_cached(kind, is_cloud()).copy()
    except Exception as e:
        st.error(f"⚠️ تعذّر قراءة البيانات: {e}")
        return _normalize(pd.DataFrame(), KINDS[kind]["cols"])


@st.cache_data(ttl=600, show_spinner=False)
def _employees_cached(cloud: bool) -> pd.DataFrame:
    if cloud:
        df = sb.read_employees()
        if df is not None and not df.empty:
            return df
    if os.path.exists(EMP_PATH):
        return pd.read_excel(EMP_PATH)
    return pd.DataFrame()


def employees() -> pd.DataFrame:
    try:
        return _employees_cached(is_cloud())
    except Exception as e:
        st.error(f"⚠️ تعذّر قراءة الموظفين: {e}")
        return pd.DataFrame()


def refresh():
    """يمسح الكاش عشان القراءة الجاية تبقى من المصدر مباشرة."""
    _load_cached.clear()
    sb.clear_cache()


# -------------------------------------------------
# أرقام السجلات المتسلسلة  LV-1, LV-2 ... / AB-1, AB-2 ...
# -------------------------------------------------
def next_ids(kind: str, n: int) -> list[str]:
    k = KINDS[kind]
    if is_cloud():
        existing = sb.fetch_keys(k["table"], k["key"])
    else:
        existing = load(kind)[k["key"]].tolist()
    start = sb.next_seq(existing, k["prefix"])
    return [f"{k['prefix']}-{start + i}" for i in range(n)]


# -------------------------------------------------
# الحفظ — إضافة / تعديل / حذف السجلات المتغيرة بس
# -------------------------------------------------
def apply_changes(kind: str, inserts: list[dict], updates: dict, deletes: list[str]) -> dict:
    """
    inserts: سجلات جديدة (من غير رقم — الرقم بيتولد هنا)
    updates: {رقم_السجل: {عمود: قيمة جديدة}}
    deletes: [أرقام السجلات المحذوفة]
    """
    k = KINDS[kind]
    key, cols = k["key"], k["cols"]
    now = pd.Timestamp.now()

    if inserts:
        ids = next_ids(kind, len(inserts))
        for rec, new_id in zip(inserts, ids):
            rec[key] = new_id
            rec.setdefault("created_at", now)
            if not fmt_id(rec.get("employee_no")):
                rec["employee_no"] = rec.get("employee_id")

    if is_cloud():
        if inserts:
            sb.insert_rows(k["table"], [sb.db_row(r, cols) for r in inserts])
        for rid, fields in updates.items():
            row = sb.db_row(fields, cols, only=list(fields.keys()))
            sb.update_row(k["table"], key, rid, row)
        if deletes:
            sb.delete_keys(k["table"], key, deletes)
    else:
        df = load(kind)
        if deletes:
            df = df[~df[key].isin(deletes)]
        for rid, fields in updates.items():
            m = df[key] == rid
            for c, v in fields.items():
                df.loc[m, c] = v
        if inserts:
            df = pd.concat([df, pd.DataFrame(inserts)], ignore_index=True)
        out = df.copy()
        for c in DATE_COLS:
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.date
        out.to_excel(k["path"], index=False)

    refresh()
    return {"added": len(inserts), "updated": len(updates), "deleted": len(deletes)}


# -------------------------------------------------
# المرفقات
# -------------------------------------------------
def upload_attachment(uploaded_file, folder: str, employee_id: str) -> tuple[str, str]:
    if uploaded_file is None:
        return "", ""
    if is_cloud():
        return sb.upload_attachment(uploaded_file, folder, sanitize_filename(employee_id))
    ext = os.path.splitext(uploaded_file.name)[1] or ".bin"
    path = os.path.join(
        ATTACHMENTS_DIR,
        f"{folder}_{sanitize_filename(employee_id)}_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}{ext}",
    )
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return uploaded_file.name, path


def attachment_available(path: str) -> bool:
    path = safe_str(path)
    return bool(path) and (sb.is_cloud_attachment(path) or os.path.exists(path))


def read_attachment(path: str) -> bytes:
    if sb.is_cloud_attachment(path):
        return sb.download_attachment(path)
    with open(path, "rb") as f:
        return f.read()


def import_from_excel(file) -> dict:
    res = sb.import_from_excel(file)
    refresh()
    _employees_cached.clear()
    return res
