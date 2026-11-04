# =========================
# sheets_store.py
# حفظ وقراءة البيانات من Google Sheet مباشرة (بدل ملفات الإكسل المحلية)
#
# - لو بيانات "حساب الخدمة" موجودة في Streamlit Secrets تحت [gcp_service_account]
#   الموقع بيقرا ويكتب في الشيت على طول.
# - لو مش موجودة، الموقع بيرجع يشتغل على الملفات المحلية زي الأول (data/*.xlsx).
# =========================
import datetime as dt

import pandas as pd
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:  # المكتبة مش متثبتة
    gspread = None

DEFAULT_SPREADSHEET_ID = "12L5CdUtVW0HpMrdfKL6MDW6biZ4A-y_TCi9XFPpmlH4"

LEAVES_WS = "الاجازات"
ABS_WS = "الغياب والتأخير"
EMP_WS = "employees"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_SERIAL_BASE = pd.Timestamp("1899-12-30")

# أعمدة ورقة الغياب في الشيت (عربي) ← أسماء الأعمدة اللي البرنامج بيستخدمها
ABS_SEARCH_HEADER = "🔎 بحث بالاسم أو الرقم الوظيفي"
ABS_SHEET_TO_APP = {
    "رقم السجل": "record_id",
    "الرقم الوظيفي": "employee_id",
    "اسم الموظف": "name_ar",
    "القسم": "department",
    "النوع": "record_type",
    "من تاريخ": "start_date",
    "إلى تاريخ": "end_date",
    "السبب": "reason",
    "تاريخ التسجيل": "created_at",
    "سجّله": "created_by",
}
ABS_HEADERS = [
    ABS_SEARCH_HEADER, "الرقم الوظيفي", "اسم الموظف", "القسم", "النوع",
    "من تاريخ", "إلى تاريخ", "السبب", "رقم السجل", "تاريخ التسجيل", "سجّله",
]


# -------------------------------------------------
# الاتصال
# -------------------------------------------------
def is_enabled() -> bool:
    if gspread is None:
        return False
    try:
        return "gcp_service_account" in st.secrets
    except Exception:
        return False


@st.cache_resource(show_spinner=False)
def _client():
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _book():
    sid = DEFAULT_SPREADSHEET_ID
    try:
        sid = st.secrets.get("sheets", {}).get("spreadsheet_id", sid)
    except Exception:
        pass
    return _client().open_by_key(sid)


def _ws(name):
    return _book().worksheet(name)


def connection_status() -> tuple[bool, str]:
    """للعرض في الشريط الجانبي: (متصل؟، رسالة)."""
    if gspread is None:
        return False, "مكتبة gspread غير مثبتة"
    if not is_enabled():
        return False, "بيانات حساب الخدمة غير موجودة في Secrets"
    try:
        _book()
        return True, "متصل بـ Google Sheet"
    except Exception as e:
        return False, f"تعذر الاتصال بالشيت: {e}"


# -------------------------------------------------
# القراءة
# -------------------------------------------------
def _fetch(name) -> list[list]:
    """كل قيم الورقة كأرقام/نصوص خام (التواريخ كأرقام تسلسلية) — مستقلة عن لغة الشيت."""
    vals = _ws(name).get_values(
        value_render_option="UNFORMATTED_VALUE",
        date_time_render_option="SERIAL_NUMBER",
    )
    if not vals:
        return []
    width = max(len(r) for r in vals)
    return [list(r) + [""] * (width - len(r)) for r in vals]


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_cached(name) -> list[list]:
    return _fetch(name)


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_employees() -> list[list]:
    return _fetch(EMP_WS)


def clear_cache():
    _fetch_cached.clear()


def _serial_to_ts(v):
    if v is None or v == "":
        return pd.NaT
    if isinstance(v, (int, float)):
        try:
            return (_SERIAL_BASE + pd.Timedelta(days=float(v))).normalize()
        except Exception:
            return pd.NaT
    return pd.to_datetime(str(v).strip(), errors="coerce")


def _clean_id(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _to_df(values: list[list]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [str(h).strip() for h in values[0]]
    df = pd.DataFrame(values[1:], columns=header)
    df["_row"] = range(2, len(values) + 1)
    return df


def read_employees() -> pd.DataFrame:
    df = _to_df(_fetch_employees())
    if df.empty:
        return df
    df = df.drop(columns=["_row"])
    for c in ["Personnel Number", "Employee ID", "Employee No", "الرقم الوظيفي"]:
        if c in df.columns:
            df[c] = df[c].apply(_clean_id)
    if "Personnel Number" in df.columns:
        df = df[df["Personnel Number"] != ""]
    return df


def read_leaves() -> pd.DataFrame:
    df = _to_df(_fetch_cached(LEAVES_WS))
    if df.empty:
        return df
    for c in ["employee_id", "employee_no"]:
        if c in df.columns:
            df[c] = df[c].apply(_clean_id)
    if "employee_id" not in df.columns:
        return pd.DataFrame()
    df = df[df["employee_id"] != ""].copy()          # الصفوف الفاضية في الجدول
    for c in ["start_date", "end_date"]:
        if c in df.columns:
            df[c] = df[c].apply(_serial_to_ts)
    if "leave_id" not in df.columns:
        df["leave_id"] = ""
    df["leave_id"] = df["leave_id"].apply(lambda v: str(v).strip())
    # صف مسجل من غير رقم إجازة ← نديله مفتاح مؤقت عشان نقدر نعدّله أو نحذفه
    df.loc[df["leave_id"] == "", "leave_id"] = df.loc[df["leave_id"] == "", "_row"].apply(lambda r: f"ROW-{r}")
    return df.drop(columns=["_row"])


def read_absences() -> pd.DataFrame:
    try:
        df = _to_df(_fetch_cached(ABS_WS))
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    if df.empty:
        return df
    out = pd.DataFrame({app: df[sheet] if sheet in df.columns else "" for sheet, app in ABS_SHEET_TO_APP.items()})
    out["employee_id"] = out["employee_id"].apply(_clean_id)
    out = out[out["employee_id"] != ""].copy()
    out["employee_no"] = out["employee_id"]
    for c in ["start_date", "end_date"]:
        out[c] = out[c].apply(_serial_to_ts)
    out["end_date"] = out["end_date"].fillna(out["start_date"])
    out["created_at"] = out["created_at"].apply(lambda v: _serial_to_ts(v) if isinstance(v, (int, float)) else v)
    out["record_id"] = out["record_id"].apply(lambda v: str(v).strip())
    out["attachment_name"] = ""
    out["attachment_path"] = ""
    return out


# -------------------------------------------------
# الكتابة — مقارنة "الجدول الجديد" بالشيت الحالي وتنفيذ الفرق بس
# (إضافة صفوف جديدة / تعديل اللي اتغير / حذف اللي اتشال)
# -------------------------------------------------
def _fmt_date(v) -> str:
    ts = pd.to_datetime(v, errors="coerce")
    return "" if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def _fmt_datetime(v) -> str:
    ts = pd.to_datetime(v, errors="coerce")
    return "" if pd.isna(ts) else ts.strftime("%Y-%m-%d %H:%M")


def _norm(v) -> str:
    """صيغة موحّدة للمقارنة بين قيمة الشيت والقيمة الجديدة."""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    if isinstance(v, (pd.Timestamp, dt.date, dt.datetime)):
        return _fmt_date(v)
    if isinstance(v, (int, float)):
        return _clean_id(v)
    return str(v).strip()


def _col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, m = divmod(n - 1, 26)
        s = chr(65 + m) + s
    return s


def next_seq(ids, prefix: str) -> int:
    mx = 0
    for v in ids:
        s = str(v).strip()
        if s.startswith(prefix + "-") and s[len(prefix) + 1:].isdigit():
            mx = max(mx, int(s[len(prefix) + 1:]))
    return mx + 1


def _sync(ws_name: str, new_records: list[dict], key_header: str, key_prefix: str,
          is_empty_row, build_row, date_headers: set, is_record=None):
    """
    new_records: السجلات بعد التعديل (كل سجل dict فيه المفتاح "_key")
    build_row(record, header, current_row_dict) -> dict {header: value} للكتابة
    """
    ws = _ws(ws_name)
    values = _fetch(ws_name)
    if not values:
        raise RuntimeError(f"ورقة {ws_name} فاضية أو بدون عناوين")
    header = [str(h).strip() for h in values[0]]
    width = len(header)
    last_col = _col_letter(width)
    key_idx = header.index(key_header)

    current = {}      # key -> (row_number, row_dict)
    empty_rows = []
    for i, r in enumerate(values[1:], start=2):
        rd = dict(zip(header, r))
        if is_empty_row(rd):
            empty_rows.append(i)
            continue
        if is_record is not None and not is_record(rd):
            continue      # صف مش سجل كامل — نسيبه زي ما هو (ما نعدّلهوش وما نحذفهوش)
        k = _norm(r[key_idx]) or f"ROW-{i}"
        current[k] = (i, rd)

    new_by_key = {}
    for i, rec in enumerate(new_records):
        new_by_key[rec.get("_key") or f"NEW-{i}"] = rec
    updates, appends = [], []

    def row_values(rec, cur_rd):
        data = build_row(rec, header, cur_rd or {})
        out = []
        for h in header:
            if h in data:
                v = data[h]
                if h in date_headers and v not in ("", None):
                    v = _fmt_date(v)
                out.append("" if v is None or (isinstance(v, float) and pd.isna(v)) else v)
            else:
                out.append((cur_rd or {}).get(h, ""))
        return out

    def differs(h, cur_v, new_v):
        if h in date_headers:
            return _fmt_date(_serial_to_ts(cur_v)) != _fmt_date(new_v) if new_v not in ("", None) else _norm(cur_v) != ""
        return _norm(cur_v) != _norm(new_v)

    # 1) تعديل الموجود (بس لو فيه حاجة اتغيرت فعلًا)
    for k, rec in new_by_key.items():
        if k in current:
            row_no, cur_rd = current[k]
            new_vals = row_values(rec, cur_rd)
            if any(differs(h, cur_rd.get(h, ""), nv) for h, nv in zip(header, new_vals)):
                updates.append({"range": f"A{row_no}:{last_col}{row_no}", "values": [new_vals]})

    # 2) إضافة الجديد (في أول صف فاضي في الجدول، وإلا في الآخر)
    used = [_norm(r[key_idx]) for r in values[1:]]
    for k, rec in new_by_key.items():
        if k in current:
            continue
        new_vals = row_values(rec, {})
        if not _norm(new_vals[key_idx]) or _norm(new_vals[key_idx]) in used:
            new_vals[key_idx] = f"{key_prefix}-{next_seq(used, key_prefix)}"
        used.append(_norm(new_vals[key_idx]))
        if empty_rows:
            r = empty_rows.pop(0)
            updates.append({"range": f"A{r}:{last_col}{r}", "values": [new_vals]})
        else:
            appends.append(new_vals)

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")

    # 3) حذف اللي اتشال (من تحت لفوق عشان أرقام الصفوف ما تتلخبطش)
    to_delete = sorted((row for k, (row, _) in current.items() if k not in new_by_key), reverse=True)
    for r in to_delete:
        ws.delete_rows(r)

    clear_cache()


# ---------- الإجازات ----------
def save_leaves(df: pd.DataFrame):
    records = []
    for rec in df.to_dict("records"):
        k = str(rec.get("leave_id", "") or "").strip()
        rec["_key"] = k
        if k.startswith("ROW-"):
            rec["leave_id"] = ""  # مفتاح مؤقت — ما يتكتبش في الشيت
        records.append(rec)

    def build_row(rec, header, cur):
        data = {}
        for h in header:
            if h in rec and h != "_key":
                v = rec[h]
                if h == "leave_id" and not v:
                    v = cur.get("leave_id", "")
                if h in ("created_at",):
                    v = _fmt_datetime(v) if not isinstance(v, str) else v
                data[h] = v
        return data

    def is_empty(rd):
        return _norm(rd.get("employee_id", "")) == "" and _norm(rd.get("leave_id", "")) == ""

    _sync(LEAVES_WS, records, "leave_id", "LV", is_empty, build_row, {"start_date", "end_date"},
          is_record=lambda rd: _norm(rd.get("employee_id", "")) != "")


# ---------- الغياب والتأخير ----------
def save_absences(df: pd.DataFrame):
    records = []
    for rec in df.to_dict("records"):
        rec["_key"] = str(rec.get("record_id", "") or "").strip()
        records.append(rec)

    app_to_sheet = {v: k for k, v in ABS_SHEET_TO_APP.items()}

    def build_row(rec, header, cur):
        data = {}
        for app_col, sheet_col in app_to_sheet.items():
            if sheet_col in header and app_col in rec:
                v = rec[app_col]
                if app_col == "created_at":
                    v = _fmt_datetime(v) if not isinstance(v, str) else v
                if app_col == "employee_id":
                    v = _clean_id(v)
                    v = int(v) if v.isdigit() else v
                data[sheet_col] = v
        if ABS_SEARCH_HEADER in header:
            data[ABS_SEARCH_HEADER] = f"{rec.get('name_ar', '')} — {_clean_id(rec.get('employee_id', ''))}"
        return data

    def is_empty(rd):
        return _norm(rd.get("الرقم الوظيفي", "")) == "" and _norm(rd.get("رقم السجل", "")) == ""

    _sync(ABS_WS, records, "رقم السجل", "AB", is_empty, build_row, {"من تاريخ", "إلى تاريخ"},
          is_record=lambda rd: _norm(rd.get("الرقم الوظيفي", "")) != "")
