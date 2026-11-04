# =========================
# supabase_store.py
# حفظ وقراءة كل بيانات الموقع من Supabase (قاعدة بيانات دائمة)
#   - الموظفين  employees
#   - الإجازات  leaves
#   - الغياب والتأخير  absences
#   - المرفقات  (مخزن الملفات: attachments)
#
# الإعداد: في Streamlit Secrets
#   [supabase]
#   url = "https://xxxx.supabase.co"
#   key = "المفتاح السري (secret / service_role)"
# لو الإعداد مش موجود، الموقع بيرجع يشتغل على الملفات المحلية (حفظ مؤقت).
# =========================
import datetime as dt
import mimetypes
import re

import pandas as pd
import streamlit as st

try:
    from supabase import create_client
except ImportError:
    create_client = None

BUCKET = "attachments"
ATTACH_PREFIX = "sb://"          # المرفقات المحفوظة في Supabase بتبدأ بالبادئة دي
PAGE = 1000                      # Supabase بيرجّع 1000 صف بحد أقصى في الطلب الواحد

LEAVE_COLS = [
    "leave_id", "employee_id", "employee_no", "name_ar", "name_en", "department",
    "job_title", "leave_type", "start_date", "end_date", "status",
    "attachment_name", "attachment_path", "notes", "created_at", "created_by",
]
ABS_COLS = [
    "record_id", "employee_id", "employee_no", "name_ar", "department", "record_type",
    "start_date", "end_date", "reason", "attachment_name", "attachment_path",
    "created_at", "created_by",
]
EMP_COLS = [
    "employee_id", "name_ar", "name_en", "department", "job_title",
    "nationality", "attendance_calculation",
]
# أسماء أعمدة الموظفين بالشكل اللي باقي البرنامج متعود عليه
EMP_TO_APP = {
    "employee_id": "Personnel Number",
    "name_ar": "Arabic name",
    "name_en": "Search name",
    "department": "Section | Department",
    "job_title": "Contrac Profession",
    "nationality": "Nationality",
    "attendance_calculation": "attendance_calculation",
}
DATE_COLS = {"start_date", "end_date"}


# -------------------------------------------------
# الاتصال
# -------------------------------------------------
def _cfg():
    try:
        sec = st.secrets.get("supabase", {})
        return sec.get("url", ""), sec.get("key", "")
    except Exception:
        return "", ""


def is_enabled() -> bool:
    url, key = _cfg()
    return create_client is not None and bool(url) and bool(key)


@st.cache_resource(show_spinner=False)
def _client():
    url, key = _cfg()
    return create_client(url, key)


def connection_status() -> tuple[bool, str]:
    if create_client is None:
        return False, "مكتبة supabase غير مثبتة"
    if not is_enabled():
        return False, "بيانات Supabase غير موجودة في Secrets"
    try:
        _client().table("leaves").select("leave_id").limit(1).execute()
        return True, "متصل بقاعدة البيانات"
    except Exception as e:
        return False, f"تعذر الاتصال بقاعدة البيانات: {e}"


# -------------------------------------------------
# أدوات تنسيق
# -------------------------------------------------
def clean_id(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        if v.is_integer():
            return str(int(v))
    s = str(v).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    return re.sub(r"\.0+$", "", s)


def _date(v):
    ts = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def _datetime(v):
    ts = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%dT%H:%M:%S")


def _text(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if v is pd.NaT:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "nat", "none") else None


def _row_for_db(rec: dict, cols: list) -> dict:
    out = {}
    for c in cols:
        v = rec.get(c)
        if c in DATE_COLS:
            out[c] = _date(v)
        elif c == "created_at":
            out[c] = _datetime(v)
        elif c in ("employee_id", "employee_no"):
            out[c] = clean_id(v) or None
        else:
            out[c] = _text(v)
    return out


def next_seq(ids, prefix: str) -> int:
    mx = 0
    for v in ids:
        s = str(v).strip()
        if s.startswith(prefix + "-") and s[len(prefix) + 1:].isdigit():
            mx = max(mx, int(s[len(prefix) + 1:]))
    return mx + 1


# -------------------------------------------------
# القراءة
# -------------------------------------------------
def _fetch_all(table: str) -> list[dict]:
    rows, start = [], 0
    while True:
        res = _client().table(table).select("*").range(start, start + PAGE - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        start += PAGE


@st.cache_data(ttl=20, show_spinner=False)
def _fetch_cached(table: str) -> list[dict]:
    return _fetch_all(table)


def clear_cache():
    _fetch_cached.clear()


def _to_df(rows: list[dict], cols: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols].copy()
    for c in DATE_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.normalize()
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Riyadh").dt.tz_localize(None)
    for c in df.columns:
        if c not in DATE_COLS and c != "created_at":
            df[c] = df[c].apply(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else v)
    return df


def read_employees() -> pd.DataFrame:
    df = _to_df(_fetch_cached("employees"), EMP_COLS)
    if df.empty:
        return df
    return df.rename(columns=EMP_TO_APP)


def read_leaves() -> pd.DataFrame:
    return _to_df(_fetch_cached("leaves"), LEAVE_COLS)


def read_absences() -> pd.DataFrame:
    return _to_df(_fetch_cached("absences"), ABS_COLS)


# -------------------------------------------------
# الكتابة — بتقارن الجدول الجديد بالموجود وتنفذ الفرق بس
# (إضافة الجديد / تعديل اللي اتغير / حذف اللي اتشال)
# -------------------------------------------------
def _sync(table: str, key: str, prefix: str, cols: list, df: pd.DataFrame):
    cur = {r[key]: r for r in _fetch_all(table)}
    cur_cmp = {k: _row_for_db(v, cols) for k, v in cur.items()}

    used = list(cur.keys())
    new_rows = {}
    for rec in df.to_dict("records"):
        row = _row_for_db(rec, cols)
        if not row.get("employee_id"):
            continue
        k = row.get(key)
        if not k or (k in new_rows):
            k = f"{prefix}-{next_seq(used + list(new_rows.keys()), prefix)}"
            row[key] = k
        if row.get("created_at") is None and k in cur:
            row["created_at"] = cur_cmp[k].get("created_at")
        new_rows[k] = row

    to_upsert = []
    for k, row in new_rows.items():
        if k not in cur_cmp:
            if row.get("created_at") is None:
                row["created_at"] = _datetime(pd.Timestamp.now())
            to_upsert.append(row)
        elif any((row.get(c) or None) != (cur_cmp[k].get(c) or None) for c in cols if c != "created_at"):
            to_upsert.append(row)
    to_delete = [k for k in cur if k not in new_rows]

    tbl = _client().table(table)
    for i in range(0, len(to_upsert), 500):
        tbl.upsert(to_upsert[i:i + 500], on_conflict=key).execute()
    for i in range(0, len(to_delete), 200):
        tbl.delete().in_(key, to_delete[i:i + 200]).execute()
    clear_cache()
    return len(to_upsert), len(to_delete)


def save_leaves(df: pd.DataFrame):
    return _sync("leaves", "leave_id", "LV", LEAVE_COLS, df)


def save_absences(df: pd.DataFrame):
    return _sync("absences", "record_id", "AB", ABS_COLS, df)


# -------------------------------------------------
# المرفقات
# -------------------------------------------------
def upload_attachment(uploaded_file, folder: str, base_name: str) -> tuple[str, str]:
    """يرفع الملف لمخزن Supabase ويرجّع (الاسم الأصلي، المسار المحفوظ)."""
    if uploaded_file is None:
        return "", ""
    ext = (re.search(r"\.[A-Za-z0-9]+$", uploaded_file.name) or [".bin"])[0].lower()
    path = f"{folder}/{base_name}_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}{ext}"
    ctype = mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"
    _client().storage.from_(BUCKET).upload(
        path, bytes(uploaded_file.getbuffer()), {"content-type": ctype, "upsert": "true"}
    )
    return uploaded_file.name, ATTACH_PREFIX + path


def is_cloud_attachment(path: str) -> bool:
    return str(path or "").startswith(ATTACH_PREFIX)


def download_attachment(path: str) -> bytes:
    return _client().storage.from_(BUCKET).download(str(path)[len(ATTACH_PREFIX):])


# -------------------------------------------------
# نقل البيانات (مرة واحدة) من ملف Excel الخاص بـ Google Sheet
# -------------------------------------------------
def import_from_excel(xls_file) -> dict:
    """
    يقرأ ملف Excel (تنزيل Google Sheet) فيه أوراق:
      employees  /  الاجازات  /  الغياب والتأخير (اختياري)
    ويضيفهم لقاعدة البيانات. السجلات الموجودة بنفس الرقم بتتحدث، وما بيتحذفش حاجة.
    """
    book = pd.read_excel(xls_file, sheet_name=None, dtype=object)
    result = {}
    tbl = lambda t: _client().table(t)

    # ---- الموظفين ----
    emp_sheet = next((n for n in book if n.strip().lower() == "employees"), None)
    if emp_sheet:
        e = book[emp_sheet]
        pick = lambda *names: next((e[n] for n in names if n in e.columns), pd.Series([None] * len(e)))
        emp = pd.DataFrame({
            "employee_id": pick("Personnel Number", "employee_id").apply(clean_id),
            "name_ar": pick("Arabic name", "name_ar"),
            "name_en": pick("Search name", "Name", "name_en"),
            "department": pick("Section | Department", "department"),
            "job_title": pick("Contrac Profession", "job_title"),
            "nationality": pick("Nationality", "nationality"),
            "attendance_calculation": pick("attendance_calculation", "Attendance Calculation"),
        })
        emp = emp[emp["employee_id"] != ""].drop_duplicates("employee_id", keep="last")
        rows = [{c: (clean_id(r[c]) if c == "employee_id" else _text(r[c])) for c in EMP_COLS} for r in emp.to_dict("records")]
        for i in range(0, len(rows), 500):
            tbl("employees").upsert(rows[i:i + 500], on_conflict="employee_id").execute()
        result["الموظفين"] = len(rows)

    # ---- الإجازات ----
    lv_sheet = next((n for n in book if n.strip() in ("الاجازات", "الإجازات", "leaves")), None)
    if lv_sheet:
        lv = book[lv_sheet].copy()
        lv["employee_id"] = lv.get("employee_id", pd.Series(dtype=object)).apply(clean_id)
        lv = lv[lv["employee_id"] != ""].copy()
        existing = [r["leave_id"] for r in _fetch_all("leaves")]
        used = set(existing)
        rows = []
        for rec in lv.to_dict("records"):
            row = _row_for_db(rec, LEAVE_COLS)
            row["employee_no"] = row.get("employee_no") or row["employee_id"]
            row["status"] = row.get("status") or "معتمدة"
            k = row.get("leave_id")
            if not k or not re.fullmatch(r"LV-\d+", k) or k in {r["leave_id"] for r in rows}:
                k = f"LV-{next_seq(list(used), 'LV')}"
                row["leave_id"] = k
            used.add(k)
            row["created_at"] = row.get("created_at") or _datetime(pd.Timestamp.now())
            rows.append(row)
        for i in range(0, len(rows), 500):
            tbl("leaves").upsert(rows[i:i + 500], on_conflict="leave_id").execute()
        result["الإجازات"] = len(rows)

    # ---- الغياب والتأخير ----
    ab_sheet = next((n for n in book if n.strip() == "الغياب والتأخير"), None)
    if ab_sheet:
        ab = book[ab_sheet]
        m = {"رقم السجل": "record_id", "الرقم الوظيفي": "employee_id", "اسم الموظف": "name_ar",
             "القسم": "department", "النوع": "record_type", "من تاريخ": "start_date",
             "إلى تاريخ": "end_date", "السبب": "reason", "تاريخ التسجيل": "created_at", "سجّله": "created_by"}
        ab = ab.rename(columns=m)
        rows, used = [], set(r["record_id"] for r in _fetch_all("absences"))
        for rec in ab.to_dict("records"):
            row = _row_for_db(rec, ABS_COLS)
            if not row.get("employee_id") or not row.get("start_date"):
                continue
            row["employee_no"] = row["employee_id"]
            row["end_date"] = row.get("end_date") or row["start_date"]
            if not row.get("record_id") or row["record_id"] in {r["record_id"] for r in rows}:
                row["record_id"] = f"AB-{next_seq(list(used), 'AB')}"
            used.add(row["record_id"])
            row["created_at"] = row.get("created_at") or _datetime(pd.Timestamp.now())
            rows.append(row)
        for i in range(0, len(rows), 500):
            tbl("absences").upsert(rows[i:i + 500], on_conflict="record_id").execute()
        result["الغياب والتأخير"] = len(rows)

    clear_cache()
    return result
