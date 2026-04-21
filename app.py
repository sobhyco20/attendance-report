# =========================
# app.py (Streamlit)
# =========================
import os
import re
from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st

from attendance_engine import process_attendance, WEEKDAY_AR

# PDF (ReportLab)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

import arabic_reshaper
from bidi.algorithm import get_display

from streamlit_cookies_manager import EncryptedCookieManager


# =========================
# إعدادات الصفحة
# =========================
st.set_page_config(page_title="Attendance Report", layout="wide")


st.markdown("""
<style>

/* =========================
   RTL
========================= */
html, body, .stApp {
    direction: rtl;
    text-align: right;
}

/* =========================
   الخلفية العامة
========================= */
.stApp {
    background-color: #0f172a;
    color: #e5e7eb;
}

/* =========================
   الكروت العامة
========================= */
.card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 12px;
}

/* عنوان الكارت */
.card-title {
    font-size: 16px;
    font-weight: bold;
    color: #f1f5f9;
}

/* =========================
   HERO
========================= */
.hero-card {
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 22px;
    margin-bottom: 20px;
}

.hero-title {
    font-size: 24px;
    font-weight: bold;
    color: #f8fafc;
}

.hero-sub {
    font-size: 14px;
    color: #94a3b8;
}

/* =========================
   KPI
========================= */
.small-kpi {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    transition: 0.2s;
}

/* hover جميل */
.small-kpi:hover {
    transform: translateY(-3px);
    border-color: #3b82f6;
}

.small-kpi .n {
    font-size: 24px;
    font-weight: bold;
    color: #38bdf8;
}

.small-kpi .t {
    font-size: 13px;
    color: #94a3b8;
}

/* =========================
   GRID NOTES
========================= */
.grid-note {
    background: #1e293b;
    border: 1px dashed #334155;
    border-radius: 10px;
    padding: 12px;
    font-size: 13px;
    color: #cbd5f5;
}

/* =========================
   صندوق النتائج
========================= */
.net-box {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 16px;
}

.net-title {
    font-weight: bold;
    color: #f1f5f9;
}

.net-big {
    font-size: 30px;
    font-weight: bold;
}

/* ألوان الحالة */
.net-good { color: #22c55e; }
.net-bad { color: #ef4444; }
.net-mid { color: #eab308; }

/* =========================
   تحسين Streamlit
========================= */
.block-container {
    padding-top: 2rem;
    max-width: 100% !important;
}

/* النصوص داخل markdown */
div[data-testid="stMarkdownContainer"] p {
    color: #e5e7eb !important;
}

/* sidebar */
section[data-testid="stSidebar"] {
    background-color: #020617 !important;
}

            
/* =========================
   إجبار النص داخل الكروت يكون يمين
========================= */

.card,
.hero-card,
.small-kpi,
.net-box,
.grid-note {
    text-align: right !important;
    direction: rtl !important;
}

/* كل النصوص داخل الكروت */
.card *,
.hero-card *,
.small-kpi *,
.net-box *,
.grid-note * {
    text-align: right !important;
    direction: rtl !important;
}

/* إصلاح عناصر Streamlit داخل الكروت */
.card div[data-testid="stMarkdownContainer"],
.hero-card div[data-testid="stMarkdownContainer"],
.net-box div[data-testid="stMarkdownContainer"] {
    text-align: right !important;
}

/* إصلاح العناوين */
h1, h2, h3, h4, h5 {
    text-align: right !important;
}    

.footer-hint {
    font-size: 12px;
    color: #94a3b8;
    margin-top: 30px;
    padding-top: 10px;
    border-top: 1px dashed #334155;
    line-height: 1.8;
    text-align: right;
}
            
                                
</style>
""", unsafe_allow_html=True)

# =========================
# Cookies
# =========================
cookies = EncryptedCookieManager(prefix="attendance_app", password="super-secret-password-change-me")
if not cookies.ready():
    st.stop()


# =========================
# Session State Init
# =========================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "login_user" not in st.session_state:
    st.session_state["login_user"] = ""

# 🔥 حفظ آخر عملية حذف (Undo)
if "last_deleted_leave" not in st.session_state:
    st.session_state["last_deleted_leave"] = None
# =========================
# Auth helpers
# =========================
def _get_users():
    try:
        return st.secrets.get("app_auth", {}).get("users", [])
    except Exception:
        return [{"username": "admin", "password": "1234"}]


def _check_user(username: str, password: str) -> bool:
    users = _get_users()
    for u in users:
        if u.get("username") == username and u.get("password") == password:
            return True
    return False


def require_login(app_name=" التأخير والغياب والخروج المبكر"):
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = (cookies.get("logged_in", "") == "true")

    if not st.session_state.get("logged_in", False):
        st.session_state["logged_in"] = (cookies.get("logged_in", "") == "true")

    if not st.session_state.get("login_user", ""):
        st.session_state["login_user"] = cookies.get("login_user", "")

    if not st.session_state.get("logged_in", False):
        st.markdown(
            """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        .block-container{ max-width: 520px; padding-top: 80px; }
        </style>
        """,
            unsafe_allow_html=True,
        )

        st.markdown(f"## 🔐 {app_name}")
        st.caption("الرجاء تسجيل الدخول للمتابعة")

        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            submit = st.form_submit_button("دخول")

        if submit:
            if _check_user(username.strip(), password):
                st.session_state["logged_in"] = True
                st.session_state["login_user"] = username.strip()

                cookies["logged_in"] = "true"
                cookies["login_user"] = username.strip()
                cookies.save()

                st.rerun()
            else:
                st.error("❌ بيانات الدخول غير صحيحة")

        st.stop()

    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h1 style="margin:0">📊 {app_name}</h1>
            <div style="color:#666;font-weight:700">مرحبًا: {st.session_state.get("login_user", "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Paths
# =========================
EMP_PATH = os.path.join("data", "employees.xlsx")
FONT_PATH = os.path.join("fonts", "Amiri-Regular.ttf")
LOGO_PATH = os.path.join("assets", "logo.png")
SIDE_IMAGE_PATH = os.path.join("assets", "222003582.jpg")
LEAVES_PATH = os.path.join("data", "leaves.xlsx")
LEAVE_ATTACHMENTS_DIR = os.path.join("data", "leave_attachments")
os.makedirs(os.path.dirname(LEAVES_PATH), exist_ok=True)
os.makedirs(LEAVE_ATTACHMENTS_DIR, exist_ok=True)




# =========================
# Login
# =========================
require_login("نظام الحضور اليومي و الإجازات")


# =========================
# Helpers
# =========================
def load_employees_silent():
    if os.path.exists(EMP_PATH):
        try:
            return pd.read_excel(EMP_PATH)
        except Exception:
            return None
    return None


def ar(text: str) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    if not s:
        return ""
    return get_display(arabic_reshaper.reshape(s))


def t(ar_text: str, en_text: str, lang: str) -> str:
    return ar_text if lang == "ar" else en_text


def safe_str(x):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()


def fmt_date(d):
    try:
        return pd.to_datetime(d).strftime("%d-%m-%Y")
    except Exception:
        return safe_str(d)


def month_year_title(emp_row):
    y, m = "", ""
    p_to = emp_row.get("period_to", "")
    try:
        dt_to = pd.to_datetime(p_to)
        y = dt_to.year
        m = dt_to.month
    except Exception:
        pass
    if y and m:
        return f"تقرير الموظف عن شهر {m:02d} - {y}"
    return "تقرير الموظف"


def month_year_title_en(emp_row):
    y, m = "", ""
    p_to = emp_row.get("period_to", "")
    try:
        dt_to = pd.to_datetime(p_to)
        y = dt_to.year
        m = dt_to.month
    except Exception:
        pass
    if y and m:
        return f"Employee Monthly Report - {m:02d}/{y}"
    return "Employee Report"


def sanitize_filename(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80] if s else "employee"


WEEKDAY_AR = {
    "Saturday": "السبت",
    "Sunday": "الأحد",
    "Monday": "الإثنين",
    "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء",
    "Thursday": "الخميس",
    "Friday": "الجمعة",
}


def weekday_to_ar(x: str) -> str:
    s = safe_str(x)
    return WEEKDAY_AR.get(s, s)


AR_CHARS = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")


def mm_to_hhmm(m: int) -> str:
    m = int(m or 0)
    sign = "-" if m < 0 else ""
    m = abs(m)
    return f"{sign}{m//60:02d}:{m%60:02d}"


def mm_to_ar_hm(m: int) -> str:
    m = int(m or 0)
    sign = "-" if m < 0 else ""
    m = abs(m)
    h = m // 60
    mm = m % 60
    return f"{sign}{h} ساعة و {mm} دقيقة"


def ensure_leaves_file():
    if not os.path.exists(LEAVES_PATH):
        cols = [
            "leave_id", "employee_id", "employee_no", "name_ar", "name_en",
            "department", "job_title", "leave_type", "start_date", "end_date",
            "status", "attachment_name", "attachment_path", "notes",
            "created_at", "created_by",
        ]
        pd.DataFrame(columns=cols).to_excel(LEAVES_PATH, index=False)


def load_leaves() -> pd.DataFrame:
    ensure_leaves_file()

    try:
        df = pd.read_excel(LEAVES_PATH)
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "leave_id", "employee_id", "employee_no", "name_ar", "name_en",
            "department", "job_title", "leave_type", "start_date", "end_date",
            "status", "attachment_name", "attachment_path", "notes",
            "created_at", "created_by",
        ])

    # 🔥 توحيد الأعمدة
    for c in [
        "employee_id", "employee_no", "name_ar", "name_en",
        "department", "job_title", "leave_type", "status",
        "attachment_name", "attachment_path", "notes",
        "created_at", "created_by"
    ]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype("object")

    # 🔥 التواريخ
    for c in ["start_date", "end_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.normalize()

    return df
   


def save_leaves(df: pd.DataFrame):
    ensure_leaves_file()
    out = df.copy()
    for c in ["start_date", "end_date"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.date
    out.to_excel(LEAVES_PATH, index=False)


def get_employee_lookup(employees_df: pd.DataFrame | None) -> pd.DataFrame:
    if employees_df is None or employees_df.empty:
        return pd.DataFrame(columns=["employee_id", "employee_no", "name_ar", "name_en", "department", "job_title"])
    emp = employees_df.copy().rename(columns={
        "Personnel Number": "employee_id",
        "Employee ID": "employee_id",
        "Emp ID": "employee_id",
        "ID": "employee_id",
        "Arabic name": "name_ar",
        "Search name": "name_en",
        "emp_name": "name_ar",
        "Contrac Profession": "job_title",
        "Section | Department": "department",
        "Employee No": "employee_no",
        "الرقم الوظيفي": "employee_no",
    })
    if "employee_id" not in emp.columns:
        return pd.DataFrame(columns=["employee_id", "employee_no", "name_ar", "name_en", "department", "job_title"])
    if "employee_no" not in emp.columns:
        emp["employee_no"] = emp["employee_id"]
    for c in ["name_ar", "name_en", "department", "job_title"]:
        if c not in emp.columns:
            emp[c] = ""
    emp["employee_id"] = emp["employee_id"].astype(str).str.strip()
    emp["employee_no"] = emp["employee_no"].astype(str).str.strip()
    return emp[["employee_id", "employee_no", "name_ar", "name_en", "department", "job_title"]].drop_duplicates()


def find_employee_record(employees_df: pd.DataFrame | None, selected_key: str):
    lookup = get_employee_lookup(employees_df)
    if lookup.empty or not selected_key:
        return None
    key = str(selected_key).strip()
    hit = lookup[(lookup["employee_id"] == key) | (lookup["employee_no"] == key)]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def employee_option_label(row) -> str:
    return f"{safe_str(row.get('name_ar'))} — {safe_str(row.get('employee_no') or row.get('employee_id'))}"


def save_leave_attachment(uploaded_file, employee_id: str, start_date, end_date) -> tuple[str, str]:
    if uploaded_file is None:
        return "", ""
    ext = os.path.splitext(uploaded_file.name)[1] or ".bin"
    fname = f"leave_{sanitize_filename(employee_id)}_{pd.to_datetime(start_date).strftime('%Y%m%d')}_{pd.to_datetime(end_date).strftime('%Y%m%d')}{ext}"
    path = os.path.join(LEAVE_ATTACHMENTS_DIR, fname)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return uploaded_file.name, path


def add_leave_record(record: dict):
    leaves = load_leaves()
    leaves = pd.concat([leaves, pd.DataFrame([record])], ignore_index=True)
    save_leaves(leaves)


def filter_leaves(leaves_df: pd.DataFrame, employee_key: str = "", start_date=None, end_date=None) -> pd.DataFrame:
    x = leaves_df.copy() if leaves_df is not None else pd.DataFrame()
    if x.empty:
        return x
    if employee_key:
        key = str(employee_key).strip()
        x = x[(x["employee_id"].astype(str).str.strip() == key) | (x["employee_no"].astype(str).str.strip() == key)]
    if start_date is not None:
        x = x[pd.to_datetime(x["end_date"], errors="coerce") >= pd.to_datetime(start_date)]
    if end_date is not None:
        x = x[pd.to_datetime(x["start_date"], errors="coerce") <= pd.to_datetime(end_date)]
    return x.sort_values(["start_date", "end_date"], ascending=[False, False])


def expand_leave_days(leaves_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if leaves_df is None or leaves_df.empty:
        return pd.DataFrame()
    for _, r in leaves_df.iterrows():
        s = pd.to_datetime(r.get("start_date"), errors="coerce")
        e = pd.to_datetime(r.get("end_date"), errors="coerce")
        if pd.isna(s) or pd.isna(e):
            continue
        for d in pd.date_range(s, e, freq="D"):
            day_name = d.day_name()
            rows.append({
                **r.to_dict(),
                "date": d.date(),
                "weekday": day_name,
                "weekday_ar": WEEKDAY_AR.get(day_name, day_name),
            })
    return pd.DataFrame(rows)


def build_pdf(emp_row, late_emp: pd.DataFrame, abs_emp: pd.DataFrame, leave_emp: pd.DataFrame | None = None, lang: str = "ar") -> bytes:
    FONT_EN = "Helvetica"
    FONT_AR_NAME = "AR"

    if not os.path.exists(FONT_PATH):
        raise FileNotFoundError(f"Arabic font not found: {FONT_PATH}")
    try:
        pdfmetrics.registerFont(TTFont(FONT_AR_NAME, FONT_PATH))
    except Exception:
        pass

    font_main = FONT_AR_NAME if lang == "ar" else FONT_EN

    align_text = 2 if lang == "ar" else 0
    align_head = 2 if lang == "ar" else 0

    def txt(x):
        s = safe_str(x)
        return ar(s) if lang == "ar" else s

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("title", parent=styles["Title"], fontName=font_main, fontSize=15, alignment=1)
    name_style = ParagraphStyle("name", parent=styles["BodyText"], fontName=font_main, fontSize=12, alignment=1, leading=16)

    info_font = font_main if lang == "ar" else FONT_EN
    info_style = ParagraphStyle(
        "info",
        parent=styles["BodyText"],
        fontName=info_font,
        fontSize=10,
        alignment=1,
        textColor=colors.grey,
        leading=14,
    )

    note_style = ParagraphStyle(
        "note",
        parent=styles["BodyText"],
        fontName=font_main if lang == "ar" else FONT_EN,
        fontSize=10,
        alignment=2 if lang == "ar" else 0,
        textColor=colors.HexColor("#8B5CF6"),
        leading=14,
        spaceBefore=6,
        spaceAfter=6,
    )

    h_style = ParagraphStyle("h", parent=title_style, fontName=font_main, fontSize=12, alignment=align_head, spaceAfter=6)
    p_style = ParagraphStyle("p", parent=styles["BodyText"], fontName=font_main, fontSize=10.5, alignment=align_text, leading=15)
    total_style = ParagraphStyle("total", parent=p_style, fontName=font_main, fontSize=12.0, alignment=align_text, leading=18)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )

    name_ar_ = safe_str(emp_row.get("name_ar", ""))
    name_en_ = safe_str(emp_row.get("name_en", ""))
    nat = safe_str(emp_row.get("nationality", emp_row.get("nationality_raw", "")))
    emp_no = safe_str(emp_row.get("employee_no", ""))
    dept = safe_str(emp_row.get("department", ""))
    job = safe_str(emp_row.get("job_title", ""))

    title = month_year_title(emp_row) if lang == "ar" else month_year_title_en(emp_row)
    attendance_rule = safe_str(emp_row.get("attendance_calculation", "")).strip().lower()

    if lang == "ar":
        info_parts = []
        if emp_no:
            info_parts.append(f"الكود/الرقم: {emp_no}")
        if job:
            info_parts.append(f"الوظيفة: {job}")
        if dept:
            info_parts.append(f"الإدارة: {dept}")
        if nat:
            info_parts.append(f"الجنسية: {nat}")
        info_line = ar(" | ".join(info_parts))
    else:
        parts = []
        if emp_no:
            parts.append(escape(f"Employee No: {emp_no}"))
        if job:
            parts.append(f"Job Title: <font name='AR'>{ar(job)}</font>" if AR_CHARS.search(job) else escape(f"Job Title: {job}"))
        if dept:
            parts.append(f"Department: <font name='AR'>{ar(dept)}</font>" if AR_CHARS.search(dept) else escape(f"Department: {dept}"))
        if nat:
            parts.append(f"Nationality: <font name='AR'>{ar(nat)}</font>" if AR_CHARS.search(nat) else escape(f"Nationality: {nat}"))
        info_line = " | ".join(parts)

    def on_first_page(canvas, _doc):
        canvas.saveState()
        W, H = A4
        if os.path.exists(LOGO_PATH):
            try:
                img = ImageReader(LOGO_PATH)
                w = 3.0 * cm
                h = 1.4 * cm
                x = W - _doc.rightMargin - w
                y = H - _doc.topMargin - h + 0.2 * cm
                canvas.drawImage(img, x, y, width=w, height=h, mask="auto")
            except Exception:
                pass
        canvas.restoreState()

    def fmt_time(x):
        try:
            tt = pd.to_datetime(str(x), errors="coerce")
            return "" if pd.isna(tt) else tt.strftime("%H:%M")
        except Exception:
            return ""

    def rtl_row(row):
        return list(reversed(row)) if lang == "ar" else row

    def rtl_cols(widths):
        return list(reversed(widths)) if lang == "ar" else widths

    if lang == "ar":
        name_line = f"{name_ar_} — {name_en_}" if name_en_ else name_ar_
        name_paragraph = Paragraph(ar(name_line), name_style)
    else:
        en_part = escape(name_en_ or "")
        ar_part = ar(name_ar_) if name_ar_ else ""
        if en_part and ar_part:
            mixed = f"{en_part} — <font name='AR'>{ar_part}</font>"
        elif en_part:
            mixed = en_part
        else:
            mixed = f"<font name='AR'>{ar_part}</font>"
        name_paragraph = Paragraph(mixed, name_style)

    story = []
    story.append(Paragraph(txt(title), title_style))
    story.append(name_paragraph)
    story.append(Paragraph(info_line, info_style))
    story.append(Spacer(1, 6))

    if attendance_rule == "daily_hours":
        if lang == "ar":
            note = "📝 ملاحظة: يتم احتساب التأخير بعد بداية الدوام مع السماح، والخروج المبكر قبل نهاية الدوام، والإضافي بعد نهاية الدوام."
            story.append(Paragraph(ar(note), note_style))
        else:
            note = "📝 Note: Late is calculated after shift start with grace, early leave before shift end, and overtime after shift end."
            story.append(Paragraph(note, note_style))
    else:
        if lang == "ar":
            note = "📝 ملاحظة: يتم احتساب التأخير بعد بداية الدوام مع السماح، والخروج المبكر قبل نهاية الدوام المحددة."
            story.append(Paragraph(ar(note), note_style))
        else:
            note = "📝 Note: Late is calculated after shift start with grace, and early leave before official shift end."
            story.append(Paragraph(note, note_style))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.lightgrey))
    story.append(Spacer(1, 8))

    section_title = "التأخير والخروج المبكر والإضافي" if lang == "ar" else "Late / Early Leave / Overtime"
    story.append(Paragraph(txt(section_title), h_style))

    if late_emp is None or late_emp.empty:
        story.append(Paragraph(txt(t("لا يوجد بيانات", "No records", lang)), p_style))
    else:
        le = late_emp.copy()
        if "date" in le.columns:
            le = le.sort_values("date")
            le["date"] = le["date"].apply(fmt_date)

        if "worked_minutes" not in le.columns:
            le["worked_minutes"] = 0
        if "overtime_minutes" not in le.columns:
            le["overtime_minutes"] = 0
        if "early_leave_minutes" not in le.columns:
            le["early_leave_minutes"] = 0

        if attendance_rule == "daily_hours":
            rows = [rtl_row([
                txt(t("اليوم", "Day", lang)),
                txt(t("التاريخ", "Date", lang)),
                txt(t("أول بصمة", "First In", lang)),
                txt(t("آخر بصمة", "Last Out", lang)),
                txt(t("ساعات العمل", "Worked", lang)),
                txt(t("التأخير", "Late", lang)),
                txt(t("الخروج المبكر", "Early Leave", lang)),
                txt(t("الإضافي", "Overtime", lang)),
            ])]

            for _, r in le.iterrows():
                day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
                row = [
                    txt(day_val),
                    txt(safe_str(r.get("date", ""))),
                    txt(fmt_time(r.get("first_punch_time", ""))),
                    txt(fmt_time(r.get("last_punch_time", ""))),
                    txt(mm_to_hhmm(int(r.get("worked_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("late_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("early_leave_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("overtime_minutes", 0) or 0))),
                ]
                rows.append(rtl_row(row))

            widths = rtl_cols([2.2*cm, 2.7*cm, 2.2*cm, 2.2*cm, 2.6*cm, 2.2*cm, 2.6*cm, 2.2*cm])
            t1 = Table(rows, colWidths=widths)
        else:
            rows = [rtl_row([
                txt(t("اليوم", "Day", lang)),
                txt(t("التاريخ", "Date", lang)),
                txt(t("أول بصمة", "First Punch", lang)),
                txt(t("آخر بصمة", "Last Punch", lang)),
                txt(t("التأخير", "Late", lang)),
                txt(t("الخروج المبكر", "Early Leave", lang)),
            ])]

            for _, r in le.iterrows():
                day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
                row = [
                    txt(day_val),
                    txt(safe_str(r.get("date", ""))),
                    txt(fmt_time(r.get("first_punch_time", ""))),
                    txt(fmt_time(r.get("last_punch_time", ""))),
                    txt(mm_to_hhmm(int(r.get("late_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("early_leave_minutes", 0) or 0))),
                ]
                rows.append(rtl_row(row))

            widths = rtl_cols([3.0*cm, 3.2*cm, 2.8*cm, 2.8*cm, 2.8*cm, 3.0*cm])
            t1 = Table(rows, colWidths=widths)

        t1.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_main),
            ("FONTSIZE", (0, 0), (-1, 0), 10.0),
            ("FONTSIZE", (0, 1), (-1, -1), 9.2),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t1)
        story.append(Spacer(1, 8))

        total_late = int(emp_row.get("total_late_minutes", 0) or 0)
        total_early_leave = int(emp_row.get("total_early_leave_minutes", 0) or 0)
        total_overtime = int(emp_row.get("total_overtime_minutes", 0) or 0)
        total_deduction = total_late + total_early_leave

        if lang == "ar":
            story.append(Paragraph(ar(f"⏱ إجمالي التأخير: {mm_to_ar_hm(total_late)}"), total_style))
            story.append(Paragraph(ar(f"🚪 إجمالي الخروج المبكر: {mm_to_ar_hm(total_early_leave)}"), total_style))

            if attendance_rule == "daily_hours":
                story.append(Paragraph(ar(f"⬆️ إجمالي الإضافي: {mm_to_ar_hm(total_overtime)}"), total_style))
                net_minutes = total_overtime - total_deduction
                if net_minutes > 0:
                    net_line = f"✅ الصافي النهائي: إضافي {mm_to_ar_hm(net_minutes)}"
                elif net_minutes < 0:
                    net_line = f"❌ الصافي النهائي: عجز {mm_to_ar_hm(net_minutes)}"
                else:
                    net_line = "➖ الصافي النهائي: متعادل (0 دقيقة)"
                story.append(Paragraph(ar(net_line), total_style))
            else:
                story.append(Paragraph(ar(f"📌 إجمالي التأخير + الخروج المبكر: {mm_to_ar_hm(total_deduction)}"), total_style))
        else:
            story.append(Paragraph(f"Total Late: {mm_to_hhmm(total_late)}", total_style))
            story.append(Paragraph(f"Total Early Leave: {mm_to_hhmm(total_early_leave)}", total_style))
            if attendance_rule == "daily_hours":
                story.append(Paragraph(f"Total Overtime: {mm_to_hhmm(total_overtime)}", total_style))
                net_minutes = total_overtime - total_deduction
                if net_minutes > 0:
                    net_line = f"Final Net: Overtime {mm_to_hhmm(net_minutes)}"
                elif net_minutes < 0:
                    net_line = f"Final Net: Deficit {mm_to_hhmm(net_minutes)}"
                else:
                    net_line = "Final Net: Balanced (0m)"
                story.append(Paragraph(net_line, total_style))
            else:
                story.append(Paragraph(f"Total Late + Early Leave: {mm_to_hhmm(total_deduction)}", total_style))

    story.append(Spacer(1, 12))

    story.append(Paragraph(txt(t("الغياب", "Absence", lang)), h_style))
    if abs_emp is None or abs_emp.empty:
        story.append(Paragraph(txt(t("لا يوجد غياب", "No absence records", lang)), p_style))
    else:
        ae = abs_emp.copy().sort_values("date") if "date" in abs_emp.columns else abs_emp.copy()
        if "date" in ae.columns:
            ae["date"] = ae["date"].apply(fmt_date)

        rows2 = [rtl_row([
            txt(t("اليوم", "Day", lang)),
            txt(t("التاريخ", "Date", lang)),
        ])]

        for _, r in ae.iterrows():
            day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
            row = [txt(day_val), txt(safe_str(r.get("date", "")))]
            rows2.append(rtl_row(row))

        t2 = Table(rows2, colWidths=rtl_cols([6.0 * cm, 9.5 * cm]))
        t2.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_main),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t2)
        story.append(Spacer(1, 6))

        absent_days = int(emp_row.get("absent_days", 0) or 0)
        story.append(Paragraph(txt(t(f"🚫 عدد أيام الغياب: {absent_days}", f"🚫 Total Absent Days: {absent_days}", lang)), total_style))

    story.append(Spacer(1, 12))
    story.append(Paragraph(txt(t("الإجازات المعتمدة", "Approved Leaves", lang)), h_style))
    if leave_emp is None or leave_emp.empty:
        story.append(Paragraph(txt(t("لا توجد إجازات معتمدة", "No approved leaves", lang)), p_style))
    else:
        lv = leave_emp.copy().sort_values("date") if "date" in leave_emp.columns else leave_emp.copy()
        if "date" in lv.columns:
            lv["date"] = lv["date"].apply(fmt_date)
        rows3 = [rtl_row([
            txt(t("اليوم", "Day", lang)),
            txt(t("التاريخ", "Date", lang)),
            txt(t("نوع الإجازة", "Leave Type", lang)),
        ])]
        for _, r in lv.iterrows():
            day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
            rows3.append(rtl_row([
                txt(day_val),
                txt(safe_str(r.get("date", ""))),
                txt(safe_str(r.get("leave_type", "إجازة"))),
            ]))
        t3 = Table(rows3, colWidths=rtl_cols([4.5 * cm, 4.5 * cm, 6.5 * cm]))
        t3.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_main),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t3)
        story.append(Spacer(1, 6))
        leave_days = int(emp_row.get("approved_leave_days", len(lv)) or 0)
        story.append(Paragraph(txt(t(f"🏖️ عدد أيام الإجازات المعتمدة: {leave_days}", f"🏖️ Total Approved Leave Days: {leave_days}", lang)), total_style))

    doc.build(story, onFirstPage=on_first_page)
    return buf.getvalue()







from reportlab.platypus import Image as RLImage

# =========================
# دالة المرفقات (زر فقط)
# =========================
def show_leave_attachments(row):
    path = safe_str(row.get("attachment_path", ""))
    name = safe_str(row.get("attachment_name", ""))

    if not path or not os.path.exists(path):
        return "—"

    if st.button("📎", key=f"open_att_{row.get('leave_id')}"):
        st.session_state["open_attachment"] = {
            "path": path,
            "name": name
        }
        st.rerun()

    return "📎"



# =========================
# PDF (بدون عرض مرفقات)
# =========================
def build_leaves_pdf(leaves_df):
    buf = BytesIO()

    FONT_PATH = os.path.join("fonts", "Amiri-Regular.ttf")
    FONT_NAME = "AR"
    pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))

    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()

    normal_style = ParagraphStyle(
        "arabic_normal",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=12,
        alignment=2,
    )

    title_style = ParagraphStyle(
        "arabic_title",
        parent=styles["Heading2"],
        fontName=FONT_NAME,
        fontSize=14,
        alignment=2,
    )

    story = []

    for _, r in leaves_df.iterrows():

        story.append(Paragraph(ar(f"الموظف: {safe_str(r.get('name_ar'))}"), title_style))
        story.append(Spacer(1, 8))

        story.append(Paragraph(ar(f"نوع الإجازة: {safe_str(r.get('leave_type'))}"), normal_style))
        story.append(Spacer(1, 5))

        story.append(Paragraph(ar(f"من: {fmt_date(r.get('start_date'))}"), normal_style))
        story.append(Spacer(1, 5))

        story.append(Paragraph(ar(f"إلى: {fmt_date(r.get('end_date'))}"), normal_style))
        story.append(Spacer(1, 5))

        if safe_str(r.get("notes")):
            story.append(Paragraph(ar(f"ملاحظات: {safe_str(r.get('notes'))}"), normal_style))
            story.append(Spacer(1, 5))

        # 👇 فقط اسم المرفق
        att_name = safe_str(r.get("attachment_name"))
        if att_name:
            story.append(Paragraph(ar(f"📎 مرفق: {att_name}"), normal_style))

        story.append(Spacer(1, 20))

    doc.build(story)
    return buf.getvalue()





# =========================
# تشغيل المعالجة
# =========================
employees_df = load_employees_silent()
leaves_df = load_leaves()
employee_lookup = get_employee_lookup(employees_df)



if "show_leaves_result" not in st.session_state:
    st.session_state["show_leaves_result"] = False
if "show_leaves_mode" not in st.session_state:
    st.session_state["show_leaves_mode"] = "موظف محدد"
if "leave_result_df" not in st.session_state:
    st.session_state["leave_result_df"] = pd.DataFrame()
if "open_attachment" not in st.session_state:
    st.session_state["open_attachment"] = None
if "edit_leave_id" not in st.session_state:
    st.session_state["edit_leave_id"] = None
if "edit_lookup_employee" not in st.session_state:
    st.session_state["edit_lookup_employee"] = None
if "edit_lookup_leave_id" not in st.session_state:
    st.session_state["edit_lookup_leave_id"] = None





with st.sidebar:
    st.header("⚙️ الإعدادات")
    st.markdown("### 👤 المستخدم")
    st.success(f"✅ {st.session_state.get('login_user','')}")
    st.caption("يمكنك الآن إدارة الإجازات واستخراج تقريرها بدون الحاجة لرفع ملف بصمة.")



main_tab, leave_root_tab = st.tabs(["📊 تقرير البصمة", "🏖️ إدارة الإجازات"])


def build_leaves_pdf(leaves_df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    FONT_NAME = "AR_LEAVE"

    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
    except Exception:
        pass

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "leave_title",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=15,
        alignment=1,
        leading=18,
        spaceAfter=10,
        textColor=colors.black,
    )

    p_style = ParagraphStyle(
        "leave_p",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10.5,
        alignment=2,
        leading=15,
        wordWrap="RTL",
        textColor=colors.black,
    )

    total_style = ParagraphStyle(
        "leave_total",
        parent=p_style,
        fontName=FONT_NAME,
        fontSize=11.5,
        alignment=2,
        leading=16,
        spaceBefore=6,
        wordWrap="RTL",
        textColor=colors.black,
    )

    header_style = ParagraphStyle(
        "leave_header",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10,
        alignment=2,
        leading=13,
        wordWrap="RTL",
        textColor=colors.black,
    )

    cell_style = ParagraphStyle(
        "leave_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.8,
        alignment=2,
        leading=11,
        wordWrap="RTL",
        textColor=colors.black,
    )

    attachment_style = ParagraphStyle(
        "leave_attachment_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.2,
        alignment=2,
        leading=10,
        wordWrap="RTL",
        splitLongWords=True,
        textColor=colors.black,
    )

    notes_style = ParagraphStyle(
        "leave_notes_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.5,
        alignment=2,
        leading=10.5,
        wordWrap="RTL",
        splitLongWords=True,
        textColor=colors.black,
    )

    def rtl_row(row):
        return list(reversed(row))

    def make_para(value, style):
        text = safe_str(value)
        if not text:
            text = "—"
        return Paragraph(ar(text), style)

    story = [
        Paragraph(ar("تقرير الإجازات"), title_style),
        Spacer(1, 8),
    ]

    if leaves_df is None or leaves_df.empty:
        story.append(Paragraph(ar("لا توجد إجازات ضمن الفترة المحددة"), p_style))
        doc.build(story)
        return buf.getvalue()

    pdf_df = leaves_df.copy()
    pdf_df["start_date"] = pd.to_datetime(pdf_df["start_date"], errors="coerce")
    pdf_df["end_date"] = pd.to_datetime(pdf_df["end_date"], errors="coerce")

    rows = [
        rtl_row([
            Paragraph(ar("الموظف"), header_style),
            Paragraph(ar("الرقم"), header_style),
            Paragraph(ar("نوع الإجازة"), header_style),
            Paragraph(ar("من"), header_style),
            Paragraph(ar("إلى"), header_style),
            Paragraph(ar("المرفق"), header_style),
            Paragraph(ar("ملاحظات"), header_style),
        ])
    ]

    for _, r in pdf_df.iterrows():
        employee_name = safe_str(r.get("name_ar", "")) or "—"
        employee_no = safe_str(r.get("employee_no", "")) or "—"
        leave_type = safe_str(r.get("leave_type", "")) or "—"
        start_date = fmt_date(r.get("start_date"))
        end_date = fmt_date(r.get("end_date"))
        attachment_name = safe_str(r.get("attachment_name", "")) or "لا يوجد"
        notes_text = safe_str(r.get("notes", "")) or "—"

        rows.append(
            rtl_row([
                Paragraph(ar(employee_name), cell_style),
                Paragraph(ar(employee_no), cell_style),
                Paragraph(ar(leave_type), cell_style),
                Paragraph(ar(start_date), cell_style),
                Paragraph(ar(end_date), cell_style),
                Paragraph(ar(attachment_name), attachment_style),
                Paragraph(ar(notes_text), notes_style),
            ])
        )

    t_pdf = Table(
        rows,
        colWidths=[
            3.6 * cm,  # ملاحظات
            3.0 * cm,  # المرفق
            2.2 * cm,  # إلى
            2.2 * cm,  # من
            2.8 * cm,  # نوع الإجازة
            2.2 * cm,  # الرقم
            3.5 * cm,  # الموظف
        ],
        repeatRows=1,
    )

    t_pdf.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(t_pdf)
    story.append(Spacer(1, 10))
    story.append(Paragraph(ar(f"عدد السجلات: {len(pdf_df)}"), total_style))

    doc.build(story)
    return buf.getvalue()


def build_leaves_pdf(leaves_df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    FONT_NAME = "AR_LEAVE"

    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
    except Exception:
        pass

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "leave_title",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=15,
        alignment=1,
        leading=18,
        spaceAfter=10,
        textColor=colors.black,
    )

    p_style = ParagraphStyle(
        "leave_p",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10.5,
        alignment=2,
        leading=15,
        wordWrap="RTL",
        textColor=colors.black,
    )

    total_style = ParagraphStyle(
        "leave_total",
        parent=p_style,
        fontName=FONT_NAME,
        fontSize=11.5,
        alignment=2,
        leading=16,
        spaceBefore=6,
        wordWrap="RTL",
        textColor=colors.black,
    )

    header_style = ParagraphStyle(
        "leave_header",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10,
        alignment=2,
        leading=13,
        wordWrap="RTL",
        textColor=colors.black,
    )

    cell_style = ParagraphStyle(
        "leave_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.8,
        alignment=2,
        leading=11,
        wordWrap="RTL",
        textColor=colors.black,
    )

    attachment_style = ParagraphStyle(
        "leave_attachment_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.2,
        alignment=2,
        leading=10,
        wordWrap="RTL",
        splitLongWords=True,
        textColor=colors.black,
    )

    notes_style = ParagraphStyle(
        "leave_notes_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.5,
        alignment=2,
        leading=10.5,
        wordWrap="RTL",
        splitLongWords=True,
        textColor=colors.black,
    )

    def rtl_row(row):
        return list(reversed(row))

    story = [
        Paragraph(ar("تقرير الإجازات"), title_style),
        Spacer(1, 8),
    ]

    if leaves_df is None or leaves_df.empty:
        story.append(Paragraph(ar("لا توجد إجازات ضمن الفترة المحددة"), p_style))
        doc.build(story)
        return buf.getvalue()

    pdf_df = leaves_df.copy()
    pdf_df["start_date"] = pd.to_datetime(pdf_df["start_date"], errors="coerce")
    pdf_df["end_date"] = pd.to_datetime(pdf_df["end_date"], errors="coerce")

    rows = [
        rtl_row([
            Paragraph(ar("الموظف"), header_style),
            Paragraph(ar("الرقم"), header_style),
            Paragraph(ar("نوع الإجازة"), header_style),
            Paragraph(ar("من"), header_style),
            Paragraph(ar("إلى"), header_style),
            Paragraph(ar("المرفق"), header_style),
            Paragraph(ar("ملاحظات"), header_style),
        ])
    ]

    for _, r in pdf_df.iterrows():
        employee_name = safe_str(r.get("name_ar", "")) or "—"
        employee_no = safe_str(r.get("employee_no", "")) or "—"
        leave_type = safe_str(r.get("leave_type", "")) or "—"
        start_date = fmt_date(r.get("start_date"))
        end_date = fmt_date(r.get("end_date"))
        attachment_name = safe_str(r.get("attachment_name", "")) or "لا يوجد"
        notes_text = safe_str(r.get("notes", "")) or "—"

        rows.append(
            rtl_row([
                Paragraph(ar(employee_name), cell_style),
                Paragraph(ar(employee_no), cell_style),
                Paragraph(ar(leave_type), cell_style),
                Paragraph(ar(start_date), cell_style),
                Paragraph(ar(end_date), cell_style),
                Paragraph(ar(attachment_name), attachment_style),
                Paragraph(ar(notes_text), notes_style),
            ])
        )

    t_pdf = Table(
        rows,
        colWidths=[
            3.6 * cm,
            3.0 * cm,
            2.2 * cm,
            2.2 * cm,
            2.8 * cm,
            2.2 * cm,
            3.5 * cm,
        ],
        repeatRows=1,
    )

    t_pdf.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(t_pdf)
    story.append(Spacer(1, 10))
    story.append(Paragraph(ar(f"عدد السجلات: {len(pdf_df)}"), total_style))

    doc.build(story)
    return buf.getvalue()


def render_leave_results_table(res: pd.DataFrame):
    display_df = res.copy()
    display_df["من"] = display_df["start_date"].apply(fmt_date)
    display_df["إلى"] = display_df["end_date"].apply(fmt_date)
    display_df["الموظف"] = display_df["name_ar"].apply(safe_str)
    display_df["الرقم الوظيفي"] = display_df["employee_no"].apply(safe_str)
    display_df["النوع"] = display_df["leave_type"].apply(safe_str)
    display_df["الحالة"] = display_df["status"].apply(safe_str)
    display_df["المرفق"] = display_df["attachment_name"].apply(lambda x: "📎" if safe_str(x) else "—")
    display_df["ملاحظات"] = display_df["notes"].apply(safe_str)

    table_df = display_df[[
        "الموظف",
        "الرقم الوظيفي",
        "النوع",
        "من",
        "إلى",
        "الحالة",
        "المرفق",
        "ملاحظات",
    ]].reset_index(drop=True)

    st.dataframe(table_df, use_container_width=True, hide_index=True)


def show_attachment_dialog_if_needed():
    if st.session_state.get("open_attachment"):
        att = st.session_state["open_attachment"]
        path = safe_str(att.get("path", ""))
        name = safe_str(att.get("name", ""))

        if path and os.path.exists(path):
            @st.dialog("📎 عرض المرفق")
            def open_attachment_dialog():
                ext = os.path.splitext(path)[1].lower()

                if ext in [".png", ".jpg", ".jpeg"]:
                    st.image(path, caption=name or os.path.basename(path), use_container_width=True)
                    with open(path, "rb") as f:
                        st.download_button(
                            "تحميل الملف",
                            data=f.read(),
                            file_name=name or os.path.basename(path),
                            use_container_width=True,
                            key=f"dlg_dl_img_{safe_str(att.get('leave_id', ''))}"
                        )
                else:
                    st.info(name or os.path.basename(path))
                    with open(path, "rb") as f:
                        st.download_button(
                            "تحميل الملف",
                            data=f.read(),
                            file_name=name or os.path.basename(path),
                            use_container_width=True,
                            key=f"dlg_dl_file_{safe_str(att.get('leave_id', ''))}"
                        )

                if st.button("إغلاق", use_container_width=True, key=f"dlg_close_{safe_str(att.get('leave_id', ''))}"):
                    st.session_state["open_attachment"] = None
                    st.rerun()

            open_attachment_dialog()
        else:
            st.session_state["open_attachment"] = None








with leave_root_tab:
    register_tab, view_tab, edit_tab = st.tabs(["➕ تسجيل إجازة", "📊 عرض الإجازات", "✏️ تعديل الإجازات"])

    with register_tab:
        st.markdown('<div class="card"><div class="card-title">➕ تسجيل إجازة جديدة</div>', unsafe_allow_html=True)

        if employee_lookup.empty:
            st.warning("ملف الموظفين غير متوفر، لذلك لا يمكن تسجيل الإجازات.")
        else:
            options_map = {
                employee_option_label(r): (r.get("employee_id") or r.get("employee_no"))
                for _, r in employee_lookup.iterrows()
            }

            with st.form("leave_form", clear_on_submit=True):
                selected_label = st.selectbox(
                    "الموظف",
                    options=list(options_map.keys()),
                    index=None,
                    placeholder="ابحث باسم الموظف..."
                )

                leave_type = st.selectbox(
                    "نوع الإجازة",
                    ["سنوية", "مرضية", "بدون راتب", "اضطرارية", "رسمية", "أخرى"]
                )

                c1, c2 = st.columns(2)
                with c1:
                    leave_start = st.date_input("من تاريخ", key="leave_start_date")
                with c2:
                    leave_end = st.date_input("إلى تاريخ", key="leave_end_date")

                notes = st.text_area("ملاحظات", key="leave_notes_field")
                leave_file = st.file_uploader(
                    "إرفاق ملف الإجازة",
                    type=["pdf", "png", "jpg", "jpeg", "doc", "docx"],
                    key="leave_attachment_upload"
                )

                submitted = st.form_submit_button("💾 حفظ الإجازة")

            if submitted:
                if not selected_label:
                    st.error("اختر الموظف أولاً")
                elif leave_end < leave_start:
                    st.error("تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية")
                else:
                    key = options_map[selected_label]
                    emp = find_employee_record(employees_df, key)

                    if not emp:
                        st.error("تعذر العثور على بيانات الموظف")
                    else:
                        attachment_name, attachment_path = save_leave_attachment(
                            leave_file,
                            safe_str(emp.get("employee_id")),
                            leave_start,
                            leave_end
                        )

                        add_leave_record({
                            "leave_id": f"LV-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}",
                            "employee_id": safe_str(emp.get("employee_id")),
                            "employee_no": safe_str(emp.get("employee_no")),
                            "name_ar": safe_str(emp.get("name_ar")),
                            "name_en": safe_str(emp.get("name_en")),
                            "department": safe_str(emp.get("department")),
                            "job_title": safe_str(emp.get("job_title")),
                            "leave_type": leave_type,
                            "start_date": pd.Timestamp(leave_start),
                            "end_date": pd.Timestamp(leave_end),
                            "status": "معتمدة",
                            "attachment_name": attachment_name,
                            "attachment_path": attachment_path,
                            "notes": notes,
                            "created_at": pd.Timestamp.now(),
                            "created_by": st.session_state.get("login_user"),
                        })

                        st.success("تم حفظ الإجازة بنجاح")
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with view_tab:
        st.markdown('<div class="card"><div class="card-title">📊 عرض وتقارير الإجازات</div>', unsafe_allow_html=True)

        if employee_lookup.empty:
            st.info("ملف الموظفين غير متوفر.")
        else:
            options_map = {
                employee_option_label(r): (r.get("employee_id") or r.get("employee_no"))
                for _, r in employee_lookup.iterrows()
            }

            view_mode = st.radio("نوع العرض", ["موظف محدد", "كل الموظفين"], key="leave_view_mode")
            c1, c2 = st.columns(2)
            with c1:
                report_from = st.date_input("من تاريخ", key="leave_report_from")
            with c2:
                report_to = st.date_input("إلى تاريخ", key="leave_report_to")

            selected_emp = None
            selected_emp_key = ""
            if view_mode == "موظف محدد":
                selected_emp = st.selectbox(
                    "اختر الموظف",
                    options=list(options_map.keys()),
                    index=None,
                    placeholder="ابحث باسم الموظف...",
                    key="leave_report_selected_emp"
                )
                if selected_emp:
                    selected_emp_key = str(options_map[selected_emp])

            btn1, btn2 = st.columns(2)
            with btn1:
                if view_mode == "موظف محدد":
                    show_clicked = st.button("📄 عرض إجازات الموظف", use_container_width=True, key="show_emp_leaves_btn")
                else:
                    show_clicked = st.button("📋 عرض كل الإجازات", use_container_width=True, key="show_all_leaves_btn")
            with btn2:
                clear_clicked = st.button("🧹 مسح العرض", use_container_width=True, key="clear_leave_view_btn")

            if clear_clicked:
                st.session_state["show_leaves_result"] = False
                st.session_state["leave_result_df"] = pd.DataFrame()
                st.rerun()

            if show_clicked:
                df = load_leaves().copy()
                if df.empty:
                    st.session_state["show_leaves_result"] = True
                    st.session_state["leave_result_df"] = pd.DataFrame()
                else:
                    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
                    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

                    if view_mode == "موظف محدد":
                        if not selected_emp:
                            st.warning("اختر الموظف أولاً")
                            st.session_state["show_leaves_result"] = False
                        else:
                            df = df[df["employee_id"].astype(str).str.strip() == str(selected_emp_key).strip()]
                            mask = (df["start_date"] <= pd.to_datetime(report_to)) & (df["end_date"] >= pd.to_datetime(report_from))
                            st.session_state["leave_result_df"] = df[mask].sort_values(["start_date", "end_date"], ascending=[False, False]).copy()
                            st.session_state["show_leaves_result"] = True
                    else:
                        mask = (df["start_date"] <= pd.to_datetime(report_to)) & (df["end_date"] >= pd.to_datetime(report_from))
                        st.session_state["leave_result_df"] = df[mask].sort_values(["start_date", "end_date"], ascending=[False, False]).copy()
                        st.session_state["show_leaves_result"] = True

            if st.session_state.get("show_leaves_result", False):
                res = st.session_state.get("leave_result_df", pd.DataFrame())

                if res is None or res.empty:
                    st.info("لا توجد إجازات ضمن الشروط المحددة.")
                else:
                    st.write(f"عدد السجلات: {len(res)}")
                    render_leave_results_table(res)


                    st.markdown("### إجراءات السجلات")
                    action_rows = res.reset_index(drop=True)
                    for idx, r in action_rows.iterrows():
                        with st.container(border=True):
                            a1, a2, a3, a4, a5 = st.columns([3, 2, 2, 1, 1])

                            with a1:
                                st.markdown(f"**{safe_str(r.get('name_ar'))}**")
                                st.caption(safe_str(r.get("employee_no")))

                            with a2:
                                st.write(f"📌 {safe_str(r.get('leave_type'))}")

                            with a3:
                                st.write(f"📅 {fmt_date(r.get('start_date'))} → {fmt_date(r.get('end_date'))}")

                            with a4:
                                has_attachment = bool(safe_str(r.get("attachment_path", ""))) and os.path.exists(safe_str(r.get("attachment_path", "")))
                                if has_attachment:
                                    if st.button("📎", key=f"att_btn_{safe_str(r.get('leave_id'))}_{idx}", use_container_width=True):
                                        st.session_state["open_attachment"] = {
                                            "path": safe_str(r.get("attachment_path", "")),
                                            "name": safe_str(r.get("attachment_name", "")),
                                            "leave_id": safe_str(r.get("leave_id", "")),
                                        }
                                        st.rerun()
                                else:
                                    st.write("—")

                            with a5:
                                col_edit, col_del = st.columns(2)

                                # ✏️ تعديل
                                with col_edit:
                                    if st.button("✏️", key=f"edit_btn_{safe_str(r.get('leave_id'))}_{idx}", use_container_width=True):
                                        st.session_state["edit_leave_id"] = safe_str(r.get("leave_id"))
                                        st.rerun()

                                # 🗑️ حذف
                                with col_del:
                                    if st.button("🗑️", key=f"del_btn_{safe_str(r.get('leave_id'))}_{idx}", use_container_width=True):

                                        leaves = load_leaves().copy()

                                        target_id = safe_str(r.get("leave_id"))

                                        # 🔥 تأكيد تطابق قوي
                                        leaves["leave_id"] = leaves["leave_id"].astype(str).str.strip()

                                        # 💾 حفظ السجل قبل الحذف
                                        deleted_row = leaves[leaves["leave_id"] == target_id]
                                        if not deleted_row.empty:
                                            st.session_state["last_deleted_leave"] = deleted_row.iloc[0].to_dict()

                                        # ❌ حذف فعلي
                                        leaves = leaves[leaves["leave_id"] != target_id]

                                        save_leaves(leaves)

                                        st.success("تم حذف الإجازة")
                                        st.rerun()





                # 🔁 زر التراجع عن الحذف
                if st.session_state.get("last_deleted_leave"):

                    st.warning("تم حذف سجل. يمكنك التراجع.")

                    if st.button("↩️ التراجع عن آخر حذف", use_container_width=True):

                        leaves = load_leaves().copy()

                        # استرجاع السجل
                        leaves = pd.concat([
                            leaves,
                            pd.DataFrame([st.session_state["last_deleted_leave"]])
                        ], ignore_index=True)

                        save_leaves(leaves)

                        st.session_state["last_deleted_leave"] = None

                        st.success("تم استرجاع الإجازة بنجاح")
                        st.rerun()
                        

                    pdf_bytes = build_leaves_pdf(res)
                    pdf_name = "leave_report_all.pdf" if view_mode == "كل الموظفين" else f"leave_report_{sanitize_filename(selected_emp_key)}.pdf"
                    st.download_button(
                        "📄 تحميل تقرير PDF",
                        data=pdf_bytes,
                        file_name=pdf_name,
                        mime="application/pdf",
                        use_container_width=True,
                        key="leave_pdf_download_btn"
                    )

        st.markdown("</div>", unsafe_allow_html=True)

    with edit_tab:
        st.markdown('<div class="card"><div class="card-title">✏️ تعديل الإجازات</div>', unsafe_allow_html=True)

        if employee_lookup.empty:
            st.info("ملف الموظفين غير متوفر.")
        else:
            options_map = {
                employee_option_label(r): (r.get("employee_id") or r.get("employee_no"))
                for _, r in employee_lookup.iterrows()
            }

            hint_text = "اختر موظفًا ثم اختر سجل الإجازة المطلوب تعديله."
            if st.session_state.get("edit_leave_id"):
                hint_text = "تم تحميل سجل من شاشة العرض. يمكنك تعديله مباشرة أو اختيار سجل آخر."
            st.markdown(f'<div class="edit-hint">{hint_text}</div>', unsafe_allow_html=True)

            preselected_emp = None
            preselected_leave_id = st.session_state.get("edit_leave_id")
            if preselected_leave_id:
                all_lv = load_leaves().copy()
                hit = all_lv[all_lv["leave_id"].astype(str).str.strip() == str(preselected_leave_id).strip()]
                if not hit.empty:
                    pre_emp_id = safe_str(hit.iloc[0].get("employee_id"))
                    for lbl, empkey in options_map.items():
                        if str(empkey).strip() == pre_emp_id:
                            preselected_emp = lbl
                            break

            edit_employee_label = st.selectbox(
                "الموظف",
                options=list(options_map.keys()),
                index=list(options_map.keys()).index(preselected_emp) if preselected_emp in list(options_map.keys()) else None,
                placeholder="ابحث باسم الموظف...",
                key="edit_lookup_employee_select"
            )

            employee_leaves = pd.DataFrame()
            selected_leave_option = None
            selected_edit_id = None

            if edit_employee_label:
                edit_employee_key = str(options_map[edit_employee_label]).strip()
                employee_leaves = load_leaves().copy()
                if not employee_leaves.empty:
                    employee_leaves["start_date"] = pd.to_datetime(employee_leaves["start_date"], errors="coerce")
                    employee_leaves["end_date"] = pd.to_datetime(employee_leaves["end_date"], errors="coerce")
                    employee_leaves = employee_leaves[
                        employee_leaves["employee_id"].astype(str).str.strip() == edit_employee_key
                    ].sort_values(["start_date", "end_date"], ascending=[False, False]).copy()

                if not employee_leaves.empty:
                    leave_options = {}
                    for _, rr in employee_leaves.iterrows():
                        label = f"{fmt_date(rr.get('start_date'))} → {fmt_date(rr.get('end_date'))} | {safe_str(rr.get('leave_type'))} | {safe_str(rr.get('leave_id'))}"
                        leave_options[label] = safe_str(rr.get("leave_id"))

                    default_label = None
                    if preselected_leave_id:
                        for lbl, lid in leave_options.items():
                            if str(lid).strip() == str(preselected_leave_id).strip():
                                default_label = lbl
                                break

                    selected_leave_option = st.selectbox(
                        "سجل الإجازة",
                        options=list(leave_options.keys()),
                        index=list(leave_options.keys()).index(default_label) if default_label in list(leave_options.keys()) else 0,
                        key="edit_lookup_leave_select"
                    )
                    selected_edit_id = leave_options[selected_leave_option]

            if selected_edit_id:
                leaves = load_leaves().copy()
                leaves["start_date"] = pd.to_datetime(leaves["start_date"], errors="coerce")
                leaves["end_date"] = pd.to_datetime(leaves["end_date"], errors="coerce")
                row = leaves[leaves["leave_id"].astype(str).str.strip() == str(selected_edit_id).strip()]

                if not row.empty:
                    r = row.iloc[0]

                    leave_types = ["سنوية", "مرضية", "بدون راتب", "اضطرارية", "رسمية", "أخرى"]
                    current_type = safe_str(r.get("leave_type"))
                    current_index = leave_types.index(current_type) if current_type in leave_types else 0

                    e1, e2 = st.columns(2)
                    with e1:
                        st.text_input("الموظف", value=safe_str(r.get("name_ar")), disabled=True, key=f"edit_name_{selected_edit_id}")
                    with e2:
                        st.text_input("الرقم الوظيفي", value=safe_str(r.get("employee_no")), disabled=True, key=f"edit_no_{selected_edit_id}")

                    new_type = st.selectbox("نوع الإجازة", leave_types, index=current_index, key=f"edit_type_{selected_edit_id}")

                    d1, d2 = st.columns(2)
                    with d1:
                        new_start = st.date_input("من", value=pd.to_datetime(r["start_date"]).date(), key=f"edit_start_{selected_edit_id}")
                    with d2:
                        new_end = st.date_input("إلى", value=pd.to_datetime(r["end_date"]).date(), key=f"edit_end_{selected_edit_id}")

                    new_notes = st.text_area("ملاحظات", value=safe_str(r.get("notes")), key=f"edit_notes_{selected_edit_id}")
                    current_name = safe_str(r.get("attachment_name"))
                    st.text_input("المرفق الحالي", value=current_name if current_name else "لا يوجد", disabled=True, key=f"edit_current_att_name_{selected_edit_id}")

                    new_file = st.file_uploader(
                        "استبدال المرفق (اختياري)",
                        type=["pdf", "png", "jpg", "jpeg", "doc", "docx"],
                        key=f"edit_file_{selected_edit_id}"
                    )

                    ec1, ec2 = st.columns(2)
                    with ec1:
                        if st.button("💾 حفظ التعديل", key=f"save_edit_{selected_edit_id}", use_container_width=True):
                            if new_end < new_start:
                                st.error("تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية")
                            else:
                                mask = leaves["leave_id"].astype(str).str.strip() == str(selected_edit_id).strip()
                                leaves.loc[mask, "leave_type"] = new_type
                                leaves.loc[mask, "start_date"] = pd.Timestamp(new_start)
                                leaves.loc[mask, "end_date"] = pd.Timestamp(new_end)
                                leaves.loc[mask, "notes"] = new_notes

                                if new_file is not None:
                                    name, path = save_leave_attachment(
                                        new_file,
                                        safe_str(r.get("employee_id")),
                                        new_start,
                                        new_end
                                    )
                                    leaves.loc[mask, "attachment_name"] = name
                                    leaves.loc[mask, "attachment_path"] = path

                                save_leaves(leaves)
                                st.success("تم تعديل الإجازة بنجاح")
                                st.session_state["edit_leave_id"] = None
                                st.rerun()

                    with ec2:
                        if st.button("❌ إلغاء التحميل", key=f"cancel_edit_{selected_edit_id}", use_container_width=True):
                            st.session_state["edit_leave_id"] = None
                            st.rerun()
                else:
                    st.warning("لم يتم العثور على سجل الإجازة.")
            else:
                st.info("اختر الموظف ثم اختر سجل الإجازة ليظهر نموذج التعديل.")

        st.markdown("</div>", unsafe_allow_html=True)

    show_attachment_dialog_if_needed()


with main_tab:
    with st.sidebar:
        uploaded_file = st.file_uploader("📄 ارفع ملف البصمة (Excel)", type=["xlsx", "xls"], key="att_file")
        start_time = st.time_input("🕗 وقت بداية الدوام", value=pd.to_datetime("08:00").time(), key="start_time")
        grace = st.number_input("⏱ دقائق السماح", min_value=0, max_value=120, value=15, key="grace")
        st.caption("ℹ️ يتم استخراج التقرير تلقائيًا بمجرد رفع الملف.")



    if not uploaded_file:
        st.markdown(
            """
            <div class="hero-card">
              <div class="hero-title">📊 لوحة تقرير البصمة</div>
              <div class="hero-sub">ارفع ملف البصمة من الشريط الجانبي لعرض التقرير الكامل مع التأخير والغياب والخروج المبكر والإجازات المعتمدة.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        a1, a2, a3 = st.columns(3)
        a1.markdown('<div class="grid-note">⏱ احتساب التأخير يتم تلقائيًا حسب وقت البداية + السماح.</div>', unsafe_allow_html=True)
        a2.markdown('<div class="grid-note">🏖️ الإجازات المعتمدة يتم استبعادها من الغياب تلقائيًا.</div>', unsafe_allow_html=True)
        a3.markdown('<div class="grid-note">📄 يمكنك تصدير تقرير الموظف PDF عربي وإنجليزي بعد رفع الملف.</div>', unsafe_allow_html=True)
    else:
        summary, late, absence, exempt_report, approved_leave_days = process_attendance(
            uploaded_file,
            start_time=start_time.strftime("%H:%M"),
            grace_minutes=int(grace),
            schedule_mode="by_nationality",
            employees_df=employees_df,
            daily_required_hours=9.0,
            approved_leaves_df=leaves_df,
        )

        if summary is None or summary.empty:
            st.error("لا توجد بيانات بعد المعالجة.")
        elif len(summary) != 1:
            st.warning("الملف يحتوي أكثر من موظف — هذا العرض مصمم لموظف واحد حاليًا.")
            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            emp = summary.iloc[0]
            emp_personnel_id = safe_str(emp.get("employee_id", ""))
            emp_no = safe_str(emp.get("employee_no", ""))
            name_ar = safe_str(emp.get("name_ar", ""))
            name_en = safe_str(emp.get("name_en", ""))
            nat = safe_str(emp.get("nationality", emp.get("nationality_raw", "")))
            dept = safe_str(emp.get("department", ""))
            job = safe_str(emp.get("job_title", ""))

            late_emp = late[late["employee_id"].astype(str).str.strip() == emp_personnel_id].copy() if late is not None and not late.empty else pd.DataFrame()
            abs_emp = absence[absence["employee_id"].astype(str).str.strip() == emp_personnel_id].copy() if absence is not None and not absence.empty else pd.DataFrame()
            leave_emp = approved_leave_days[approved_leave_days["employee_id"].astype(str).str.strip() == emp_personnel_id].copy() if approved_leave_days is not None and not approved_leave_days.empty else pd.DataFrame()

            if not late_emp.empty and "weekday" in late_emp.columns:
                late_emp["weekday_ar"] = late_emp["weekday"].apply(weekday_to_ar)
            if not abs_emp.empty and "weekday" in abs_emp.columns:
                abs_emp["weekday_ar"] = abs_emp["weekday"].apply(weekday_to_ar)
            if not leave_emp.empty and "weekday" in leave_emp.columns:
                leave_emp["weekday_ar"] = leave_emp["weekday"].apply(weekday_to_ar)

            pdf_ar = build_pdf(emp, late_emp, abs_emp, leave_emp, lang="ar")
            pdf_en = build_pdf(emp, late_emp, abs_emp, leave_emp, lang="en")

            st.session_state["pdf_bytes_ar"] = pdf_ar
            st.session_state["pdf_bytes_en"] = pdf_en
            base_name = sanitize_filename(name_ar or name_en)
            base_no = sanitize_filename(emp_no)
            st.session_state["pdf_filename_ar"] = f"{base_name}_{base_no}_AR.pdf"
            st.session_state["pdf_filename_en"] = f"{base_name}_{base_no}_EN.pdf"

            title = month_year_title(emp)
            schedule = safe_str(emp.get("schedule", ""))
            sat_note = "✅ دوام السبت" if schedule == "جمعة فقط" else "🛑 إجازة السبت"
            fri_note = "🛑 إجازة الجمعة"

            st.markdown(
                f"""
                <div class="hero-card">
                <div class="hero-title">{title}</div>
                <div class="hero-sub">{fri_note} • {sat_note}</div>
                <div style="font-size:28px;font-weight:1000;margin-top:10px">👤 {name_ar}</div>
                <div class="hero-sub">{name_en}</div>
                <div class="hero-sub" style="margin-top:4px">{nat} • {job} • {dept}</div>
                <div style="margin-top:10px;font-weight:900">الكود / الرقم الوظيفي: {emp_no}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.markdown(f'<div class="small-kpi"><div class="n">{int(emp.get("total_late_minutes",0) or 0)}</div><div class="t">إجمالي دقائق التأخير</div></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="small-kpi"><div class="n">{int(emp.get("total_early_leave_minutes",0) or 0)}</div><div class="t">إجمالي دقائق الخروج المبكر</div></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="small-kpi"><div class="n">{int(emp.get("late_days",0) or 0)}</div><div class="t">عدد أيام التأخير</div></div>', unsafe_allow_html=True)
            k4.markdown(f'<div class="small-kpi"><div class="n">{int(emp.get("absent_days",0) or 0)}</div><div class="t">عدد أيام الغياب</div></div>', unsafe_allow_html=True)
            k5.markdown(f'<div class="small-kpi"><div class="n">{int(emp.get("approved_leave_days",0) or 0)}</div><div class="t">أيام الإجازات المعتمدة</div></div>', unsafe_allow_html=True)

            k6, k7 = st.columns(2)
            k6.markdown(f'<div class="small-kpi"><div class="n">{int(emp.get("early_leave_days",0) or 0)}</div><div class="t">عدد أيام الخروج المبكر</div></div>', unsafe_allow_html=True)
            k7.markdown(f'<div class="small-kpi"><div class="n">{int((emp.get("total_late_minutes",0) or 0) + (emp.get("total_early_leave_minutes",0) or 0))}</div><div class="t">إجمالي دقائق التأخيرات الزمنية</div></div>', unsafe_allow_html=True)

            attendance_rule = safe_str(emp.get("attendance_calculation", "")).strip().lower()
            if attendance_rule == "daily_hours":
                total_late = int(emp.get("total_late_minutes", 0) or 0)
                total_early_leave = int(emp.get("total_early_leave_minutes", 0) or 0)
                total_overtime = int(emp.get("total_overtime_minutes", 0) or 0)
                total_deficit = total_late + total_early_leave
                net = total_overtime - total_deficit
                net_label = "صافي إضافي" if net > 0 else ("صافي عجز" if net < 0 else "متعادل")
                net_class = "net-good" if net > 0 else ("net-bad" if net < 0 else "net-mid")
                st.markdown(
                    f"""
                    <div class="net-box">
                      <div class="net-title">🧾 نتيجة الاحتساب للمستثنى</div>
                      <div class="net-big {net_class}">{net_label}: {mm_to_hhmm(net)}</div>
                      <div class="net-sub">الصافي = إجمالي الإضافي − (إجمالي التأخير + إجمالي الخروج المبكر)</div>
                      <div class="net-row">
                        <div class="net-pill">⬇️ إجمالي التأخير: <b>{mm_to_hhmm(total_late)}</b><span>(بعد بداية الدوام + السماح)</span></div>
                        <div class="net-pill">🚪 إجمالي الخروج المبكر: <b>{mm_to_hhmm(total_early_leave)}</b><span>(قبل نهاية الدوام)</span></div>
                        <div class="net-pill">⬆️ إجمالي الإضافي: <b>{mm_to_hhmm(total_overtime)}</b><span>(بعد نهاية الدوام)</span></div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                total_late = int(emp.get("total_late_minutes", 0) or 0)
                total_early_leave = int(emp.get("total_early_leave_minutes", 0) or 0)
                total_deficit = total_late + total_early_leave
                st.markdown(
                    f"""
                    <div class="net-box">
                      <div class="net-title">🧾 ملخص الاحتساب</div>
                      <div class="net-big net-bad">إجمالي التأخيرات: {mm_to_hhmm(total_deficit)}</div>
                      <div class="net-sub">إجمالي التأخيرات = التأخير + الخروج المبكر</div>
                      <div class="net-row">
                        <div class="net-pill">⬇️ إجمالي التأخير: <b>{mm_to_hhmm(total_late)}</b><span>(بعد بداية الدوام + السماح)</span></div>
                        <div class="net-pill">🚪 إجمالي الخروج المبكر: <b>{mm_to_hhmm(total_early_leave)}</b><span>(قبل نهاية الدوام)</span></div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            overview_tab, details_tab, status_tab = st.tabs(["📌 الملخص", "🧾 التفاصيل اليومية", "🚫 الغياب والإجازات"])

            with overview_tab:
                st.markdown('<div class="soft-card"><div class="soft-title">بطاقة الموظف</div>', unsafe_allow_html=True)
                info1, info2, info3, info4 = st.columns(4)
                info1.write(f"**الاسم العربي:** {name_ar}")
                info2.write(f"**الاسم الإنجليزي:** {name_en}")
                info3.write(f"**الجنسية:** {nat}")
                info4.write(f"**الإدارة:** {dept}")
                st.markdown("</div>", unsafe_allow_html=True)

                totals_df = pd.DataFrame([
                    {"البند": "إجمالي التأخير", "القيمة": mm_to_hhmm(int(emp.get("total_late_minutes", 0) or 0))},
                    {"البند": "إجمالي الخروج المبكر", "القيمة": mm_to_hhmm(int(emp.get("total_early_leave_minutes", 0) or 0))},
                    {"البند": "أيام الغياب", "القيمة": int(emp.get("absent_days", 0) or 0)},
                    {"البند": "أيام الإجازات المعتمدة", "القيمة": int(emp.get("approved_leave_days", 0) or 0)},
                ])
                if attendance_rule == "daily_hours":
                    totals_df = pd.concat([
                        totals_df,
                        pd.DataFrame([{"البند": "إجمالي الإضافي", "القيمة": mm_to_hhmm(int(emp.get("total_overtime_minutes", 0) or 0))}])
                    ], ignore_index=True)

                st.dataframe(totals_df, use_container_width=True, hide_index=True)

            with details_tab:
                st.markdown('<div class="soft-card"><div class="section-head"><div class="ttl">⏱ التأخير / الخروج المبكر / الإضافي</div><div class="sub">عرض يومي تفصيلي</div></div>', unsafe_allow_html=True)

                if late_emp is None or late_emp.empty:
                    st.success("لا يوجد سجلات مخالفة ✅")
                else:
                    details_df = late_emp.copy()
                    if "date" in details_df.columns:
                        details_df["date"] = pd.to_datetime(details_df["date"], errors="coerce")
                        details_df = details_df.sort_values("date")

                    details_df["التاريخ"] = details_df["date"].apply(fmt_date) if "date" in details_df.columns else ""
                    details_df["اليوم"] = details_df["weekday_ar"].apply(safe_str) if "weekday_ar" in details_df.columns else ""
                    details_df["أول بصمة"] = details_df["first_punch_time"].apply(lambda x: pd.to_datetime(str(x), errors="coerce").strftime("%H:%M") if safe_str(x) else "") if "first_punch_time" in details_df.columns else ""
                    details_df["آخر بصمة"] = details_df["last_punch_time"].apply(lambda x: pd.to_datetime(str(x), errors="coerce").strftime("%H:%M") if safe_str(x) else "") if "last_punch_time" in details_df.columns else ""
                    details_df["التأخير"] = details_df["late_minutes"].apply(mm_to_hhmm) if "late_minutes" in details_df.columns else ""
                    details_df["الخروج المبكر"] = details_df["early_leave_minutes"].apply(mm_to_hhmm) if "early_leave_minutes" in details_df.columns else ""

                    show_cols = ["اليوم", "التاريخ", "أول بصمة", "آخر بصمة", "التأخير", "الخروج المبكر"]
                    if attendance_rule == "daily_hours":
                        if "worked_minutes" in details_df.columns:
                            details_df["ساعات العمل"] = details_df["worked_minutes"].apply(mm_to_hhmm)
                            show_cols.insert(4, "ساعات العمل")
                        if "overtime_minutes" in details_df.columns:
                            details_df["الإضافي"] = details_df["overtime_minutes"].apply(mm_to_hhmm)
                            show_cols.append("الإضافي")

                    st.dataframe(details_df[show_cols], use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with status_tab:
                sc1, sc2 = st.columns(2)

                with sc1:
                    st.markdown('<div class="soft-card"><div class="soft-title">🚫 الغياب</div>', unsafe_allow_html=True)
                    if abs_emp.empty:
                        st.success("لا يوجد غياب ✅")
                    else:
                        abs_df = abs_emp.copy()
                        abs_df["التاريخ"] = abs_df["date"].apply(fmt_date) if "date" in abs_df.columns else ""
                        abs_df["اليوم"] = abs_df["weekday_ar"].apply(safe_str) if "weekday_ar" in abs_df.columns else ""
                        st.dataframe(abs_df[["اليوم", "التاريخ"]], use_container_width=True, hide_index=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                with sc2:
                    st.markdown('<div class="soft-card"><div class="soft-title">🏖️ الإجازات المعتمدة</div>', unsafe_allow_html=True)
                    if leave_emp.empty:
                        st.success("لا توجد إجازات معتمدة ضمن الفترة ✅")
                    else:
                        leave_df = leave_emp.copy()
                        leave_df["التاريخ"] = leave_df["date"].apply(fmt_date) if "date" in leave_df.columns else ""
                        leave_df["اليوم"] = leave_df["weekday_ar"].apply(safe_str) if "weekday_ar" in leave_df.columns else ""
                        leave_df["نوع الإجازة"] = leave_df["leave_type"].apply(safe_str) if "leave_type" in leave_df.columns else ""
                        leave_df["المرفق"] = leave_df["attachment_name"].apply(lambda x: safe_str(x) if safe_str(x) else "—") if "attachment_name" in leave_df.columns else "—"
                        st.dataframe(leave_df[["اليوم", "التاريخ", "نوع الإجازة", "المرفق"]], use_container_width=True, hide_index=True)
                    st.markdown("</div>", unsafe_allow_html=True)

            with st.sidebar:
                st.divider()
                st.subheader("⬇️ التصدير")
                st.markdown('<div class="export-box">', unsafe_allow_html=True)

                if st.session_state.get("pdf_bytes_ar", b""):
                    st.download_button(
                        "📄 تحميل تقرير PDF (عربي)",
                        data=st.session_state["pdf_bytes_ar"],
                        file_name=st.session_state.get("pdf_filename_ar", "report_AR.pdf"),
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_pdf_ar",
                    )

                if st.session_state.get("pdf_bytes_en", b""):
                    st.download_button(
                        "📄 Download PDF (English)",
                        data=st.session_state["pdf_bytes_en"],
                        file_name=st.session_state.get("pdf_filename_en", "report_EN.pdf"),
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_pdf_en",
                    )

                st.markdown("""
                <div class="footer-hint">
                🕋 رمضان: 09:30 → 15:30<br>
                🚪 الخروج المبكر: 17:00 (عادي) / 15:30 (رمضان)<br>
                🎉 إجازة العيد لا تُحسب غياب أو تأخير
                </div>
                """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                if os.path.exists(SIDE_IMAGE_PATH):
                    st.image(SIDE_IMAGE_PATH, use_container_width=True)

                st.divider()

                if st.button("🚪 تسجيل خروج", use_container_width=True):
                    cookies["logged_in"] = "false"
                    cookies["login_user"] = ""
                    cookies.save()
                    st.session_state["logged_in"] = False
                    st.session_state["login_user"] = ""
                    st.rerun()
