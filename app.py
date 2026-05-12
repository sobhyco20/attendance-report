# =========================
# app.py (Streamlit)
# =========================
import os
import re
from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st


from database import (
    load_leaves_db,
    insert_leave,
    delete_leave
)


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





# =========================
# Login
# =========================
require_login("تقرير التأخير والغياب والخروج المبكر")


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





def load_leaves():

    df = load_leaves_db()

    if df is None or df.empty:

        return pd.DataFrame(columns=[

            "leave_id",
            "employee_id",
            "employee_no",

            "name_ar",
            "name_en",

            "department",
            "job_title",

            "leave_type",

            "start_date",
            "end_date",

            "status",

            "attachment_name",


            "notes",

            "created_at",
            "created_by",
        ])

    # ====================================
    # توحيد أنواع البيانات
    # ====================================

    for c in [

        "employee_id",
        "employee_no",

        "name_ar",
        "name_en",

        "department",
        "job_title",

        "leave_type",

        "status",

        "attachment_name",


        "notes",

        "created_by"

    ]:

        if c not in df.columns:
            df[c] = ""

        df[c] = df[c].astype(str)

    # ====================================
    # التواريخ
    # ====================================

    for c in [

        "start_date",
        "end_date",
        "created_at"

    ]:

        if c in df.columns:

            df[c] = pd.to_datetime(
                df[c],
                errors="coerce"
            )

    return df


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



def add_leave_record(
    record: dict,
    uploaded_file=None
):

    record["uploaded_file"] = uploaded_file

    insert_leave(record)


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
        # =====================================================
        # حذف السبت نهائياً من PDF لغير السعوديين
        # =====================================================
        
        schedule_name = safe_str(
            emp_row.get("schedule", "")
        )
        
        if (
            "جمعة فقط" in schedule_name
            or
            "الجمعة فقط" in schedule_name
        ):
        
            le = le[
                le["weekday"] != "Saturday"
            ].copy()
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

                day_val = safe_str(

                    r.get(
                        "weekday_ar",
                        r.get("weekday", "")
                    )

                ) if lang == "ar" else safe_str(
                    r.get("weekday", "")
                )

                # =====================================================
                # القيم الأساسية
                # =====================================================

                worked_minutes = int(
                    r.get("worked_minutes", 0) or 0
                )

                late_minutes = int(
                    r.get("late_minutes", 0) or 0
                )

                early_leave_minutes = int(
                    r.get("early_leave_minutes", 0) or 0
                )

                overtime_minutes = int(
                    r.get("overtime_minutes", 0) or 0
                )

                weekday_name = safe_str(
                    r.get("weekday", "")
                )

                schedule_name = safe_str(
                    emp_row.get("schedule", "")
                )


                row = [

                    txt(day_val),

                    txt(
                        safe_str(
                            r.get("date", "")
                        )
                    ),

                    txt(
                        fmt_time(
                            r.get(
                                "first_punch_time",
                                ""
                            )
                        )
                    ),

                    txt(
                        fmt_time(
                            r.get(
                                "last_punch_time",
                                ""
                            )
                        )
                    ),

                    txt(
                        mm_to_hhmm(
                            worked_minutes
                        )
                    ),

                    txt(
                        mm_to_hhmm(
                            late_minutes
                        )
                    ),

                    txt(
                        mm_to_hhmm(
                            early_leave_minutes
                        )
                    ),

                    txt(
                        mm_to_hhmm(
                            overtime_minutes
                        )
                    ),

                ]

                rows.append(
                    rtl_row(row)
                )

            widths = rtl_cols([

                2.2 * cm,
                2.7 * cm,
                2.2 * cm,
                2.2 * cm,
                2.6 * cm,
                2.2 * cm,
                2.6 * cm,
                2.2 * cm,

            ])

            t1 = Table(
                rows,
                colWidths=widths
            )
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
        
        # =====================================================
        # إعادة احتساب الإجماليات من الجدول نفسه
        # لاستبعاد السبت نهائياً
        # =====================================================
        
        pdf_df = le.copy()
        
        schedule_name = safe_str(
            emp_row.get("schedule", "")
        )
        
        if (
            "جمعة فقط" in schedule_name
            or
            "الجمعة فقط" in schedule_name
        ):
        
            pdf_df = pdf_df[
                pdf_df["weekday"] != "Saturday"
            ].copy()
        
        total_late = int(
            pdf_df["late_minutes"].fillna(0).sum()
        )
        
        total_early_leave = int(
            pdf_df["early_leave_minutes"].fillna(0).sum()
        )
        
        total_overtime = int(
            pdf_df["overtime_minutes"].fillna(0).sum()
        )
        
        total_deduction = (
            total_late
            +
            total_early_leave
        )

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


from database import get_attachment

from database import get_attachment

def show_leave_attachments(row):

    leave_id = row.get("leave_id")

    if st.button(
        "📎 تحميل",
        key=f"att_{leave_id}"
    ):

        att = get_attachment(leave_id)

        if att and att["data"]:

            st.download_button(
                "⬇️ تحميل المرفق",
                data=att["data"],
                file_name=att["name"],
                key=f"download_{leave_id}"
                    )
        if st.session_state.get("refresh_leaves"):
        
            leaves_df = load_leaves()
        
            st.session_state["refresh_leaves"] = False

with leave_root_tab:

    register_tab, view_tab, edit_tab = st.tabs([
        "➕ تسجيل إجازة",
        "📊 عرض الإجازات",
        "✏️ تعديل الإجازات"
    ])

    # =========================================================
    # تسجيل إجازة
    # =========================================================

    with register_tab:

        st.markdown(
            '''
            <div class="card">
            <div class="card-title">
            ➕ تسجيل إجازة جديدة
            </div>
            ''',
            unsafe_allow_html=True
        )

        if employee_lookup.empty:

            st.warning(
                "ملف الموظفين غير متوفر، لذلك لا يمكن تسجيل الإجازات."
            )

        else:

            # =====================================================
            # خيارات الموظفين
            # =====================================================

            options_map = {

                employee_option_label(r):
                    (
                        r.get("employee_id")
                        or
                        r.get("employee_no")
                    )

                for _, r in employee_lookup.iterrows()
            }

            # =====================================================
            # الفورم اليدوي (الرئيسي)
            # =====================================================

            st.markdown("### ➕ تسجيل إجازة يدوية")

            with st.form(
                "leave_form",
                clear_on_submit=True
            ):

                selected_label = st.selectbox(

                    "الموظف",

                    options=list(options_map.keys()),

                    index=None,

                    placeholder="ابحث باسم الموظف..."

                )

                leave_type = st.selectbox(

                    "نوع الإجازة",

                    [
                        "سنوية",
                        "مرضية",
                        "بدون راتب",
                        "اضطرارية",
                        "رسمية",
                        "أخرى"
                    ]

                )

                c1, c2 = st.columns(2)

                with c1:

                    leave_start = st.date_input(
                        "من تاريخ",
                        key="leave_start_date"
                    )

                with c2:

                    leave_end = st.date_input(
                        "إلى تاريخ",
                        key="leave_end_date"
                    )

                notes = st.text_area(
                    "ملاحظات",
                    key="leave_notes_field"
                )

                leave_file = st.file_uploader(

                    "إرفاق ملف الإجازة",

                    type=[
                        "pdf",
                        "png",
                        "jpg",
                        "jpeg",
                        "doc",
                        "docx"
                    ],

                    key="leave_attachment_upload"

                )

                submitted = st.form_submit_button(
                    "💾 حفظ الإجازة"
                )

            # =====================================================
            # حفظ الإجازة
            # =====================================================

            if submitted:

                if not selected_label:

                    st.error("اختر الموظف أولاً")

                elif leave_end < leave_start:

                    st.error(
                        "تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية"
                    )

                else:

                    key = options_map[selected_label]

                    emp = find_employee_record(
                        employees_df,
                        key
                    )

                    if not emp:

                        st.error(
                            "تعذر العثور على بيانات الموظف"
                        )

                    else:

                        attachment_name = (
                            leave_file.name
                            if leave_file
                            else ""
                        )


                        add_leave_record(

                            {

                                "leave_id":
                                    f"LV-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}",

                                "employee_id":
                                    safe_str(
                                        emp.get(
                                            "employee_id"
                                        )
                                    ).replace(".0", "").strip(),

                                "employee_no":
                                    safe_str(
                                        emp.get(
                                            "employee_no"
                                        )
                                    ),

                                "name_ar":
                                    safe_str(
                                        emp.get(
                                            "name_ar"
                                        )
                                    ),

                                "name_en":
                                    safe_str(
                                        emp.get(
                                            "name_en"
                                        )
                                    ),

                                "department":
                                    safe_str(
                                        emp.get(
                                            "department"
                                        )
                                    ),

                                "job_title":
                                    safe_str(
                                        emp.get(
                                            "job_title"
                                        )
                                    ),

                                "leave_type":
                                    leave_type,

                                "start_date":
                                    pd.Timestamp(
                                        leave_start
                                    ),

                                "end_date":
                                    pd.Timestamp(
                                        leave_end
                                    ),

                                "status":
                                    "معتمدة",

                                "attachment_name":
                                    leave_file.name if leave_file else "",

                                "notes":
                                    notes,

                                "created_at":
                                    pd.Timestamp.now(),

                                "created_by":
                                    st.session_state.get(
                                        "login_user"
                                    ),

                            },

                            uploaded_file=leave_file

                        )

                        st.success(
                            "✅ تم حفظ الإجازة بنجاح"
                        )
                        st.session_state["refresh_leaves"] = True
                        st.rerun()

            # =====================================================
            # فاصل
            # =====================================================

            st.markdown("<hr>", unsafe_allow_html=True)

            # =====================================================
            # رفع ملف كامل (ثانوي)
            # =====================================================

            st.markdown("### 📥 رفع ملف إجازات كامل")

            st.caption(
                "يمكنك رفع ملف Excel يحتوي على عدة إجازات دفعة واحدة."
            )

            bulk_file = st.file_uploader(

                "ارفع ملف Excel للإجازات",

                type=["xlsx"],

                key="bulk_leave_upload"

            )

            if bulk_file:

                try:

                    bulk_df = pd.read_excel(
                        bulk_file
                    )

                    required_cols = [

                        "employee_id",
                        "leave_type",
                        "start_date",
                        "end_date"

                    ]

                    missing = [

                        c for c in required_cols

                        if c not in bulk_df.columns

                    ]

                    if missing:

                        st.error(
                            f"الأعمدة الناقصة: {missing}"
                        )

                    else:

                        bulk_df["start_date"] = (
                            pd.to_datetime(

                                bulk_df["start_date"],

                                errors="coerce"
                            )
                        )

                        bulk_df["end_date"] = (
                            pd.to_datetime(

                                bulk_df["end_date"],

                                errors="coerce"
                            )
                        )

                        inserted = 0

                        for _, r in bulk_df.iterrows():

                            emp_id = str(

                                r.get(
                                    "employee_id",
                                    ""
                                )

                            ).replace(".0", "").strip()

                            if not emp_id:
                                continue

                            emp = find_employee_record(
                                employees_df,
                                emp_id
                            )

                            add_leave_record(

                                {

                                    "leave_id":
                                        f"LV-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}",

                                    "employee_id":
                                        emp_id,

                                    "employee_no":
                                        (
                                            safe_str(
                                                emp.get(
                                                    "employee_no"
                                                )
                                            )
                                            if emp
                                            else emp_id
                                        ),

                                    "name_ar":
                                        (
                                            safe_str(
                                                emp.get(
                                                    "name_ar"
                                                )
                                            )
                                            if emp
                                            else ""
                                        ),

                                    "name_en":
                                        (
                                            safe_str(
                                                emp.get(
                                                    "name_en"
                                                )
                                            )
                                            if emp
                                            else ""
                                        ),

                                    "department":
                                        (
                                            safe_str(
                                                emp.get(
                                                    "department"
                                                )
                                            )
                                            if emp
                                            else ""
                                        ),

                                    "job_title":
                                        (
                                            safe_str(
                                                emp.get(
                                                    "job_title"
                                                )
                                            )
                                            if emp
                                            else ""
                                        ),

                                    "leave_type":
                                        str(
                                            r.get(
                                                "leave_type",
                                                "سنوية"
                                            )
                                        ),

                                    "start_date":
                                        r.get(
                                            "start_date"
                                        ),

                                    "end_date":
                                        r.get(
                                            "end_date"
                                        ),

                                    "status":
                                        "معتمدة",

                                    "attachment_name":
                                        "",

                                    "notes":
                                        str(
                                            r.get(
                                                "notes",
                                                ""
                                            )
                                        ),

                                    "created_at":
                                        pd.Timestamp.now(),

                                    "created_by":
                                        st.session_state.get(
                                            "login_user"
                                        ),

                                }

                            )
                            inserted += 1

                        st.success(
                            f"✅ تم رفع {inserted} إجازة بنجاح"
                        )

                        st.rerun()

                except Exception as e:

                    st.error(e)

        st.markdown(
            "</div>",
            unsafe_allow_html=True
        )

    # =========================================================
    # عرض الإجازات
    # =========================================================

    with view_tab:

        st.markdown("## 📊 عرض الإجازات")

        leaves_df = load_leaves()

        if leaves_df.empty:

            st.warning("لا توجد إجازات مسجلة")

        else:

            c1, c2, c3 = st.columns(3)

            with c1:

                search_emp = st.text_input(
                    "بحث باسم الموظف"
                )

            with c2:

                from_date = st.date_input(
                    "من تاريخ",
                    value=None
                )

            with c3:

                to_date = st.date_input(
                    "إلى تاريخ",
                    value=None
                )

            result = leaves_df.copy()

            # =====================================
            # فلترة الموظف
            # =====================================

            if search_emp:

                result = result[

                    result["name_ar"]

                    .astype(str)

                    .str.contains(

                        search_emp,

                        case=False,

                        na=False

                    )

                ]

            # =====================================
            # فلترة التواريخ
            # =====================================

            if from_date:

                result = result[

                    pd.to_datetime(

                        result["start_date"]

                    ) >= pd.Timestamp(from_date)

                ]

            if to_date:

                result = result[

                    pd.to_datetime(

                        result["end_date"]

                    ) <= pd.Timestamp(to_date)

                ]

            # =====================================
            # عرض الجدول
            # =====================================

            render_leave_results_table(result)

            st.markdown("### 📎 المرفقات")

            for _, row in result.iterrows():

                if safe_str(
                    row.get("attachment_name")
                ):

                    c1, c2 = st.columns([8, 2])

                    with c1:

                        st.write(

                            f"{safe_str(row.get('name_ar'))}"
                            f" - "
                            f"{safe_str(row.get('leave_type'))}"

                        )

                    with c2:

                        show_leave_attachments(row)

            # =====================================
            # PDF
            # =====================================

            pdf_bytes = build_leaves_pdf(result)

            st.download_button(

                "⬇️ تحميل PDF",

                data=pdf_bytes,

                file_name="leaves_report.pdf",

                mime="application/pdf"

            )


    # =========================================================
    # تعديل الإجازات
    # =========================================================

    with edit_tab:

        st.markdown("## ✏️ تعديل الإجازات")

        leaves_df = load_leaves()

        if leaves_df.empty:

            st.warning(
                "لا توجد إجازات للتعديل"
            )

        else:

            options = {

                f"{safe_str(r.get('name_ar'))}"
                f" | "
                f"{fmt_date(r.get('start_date'))}"
                f" → "
                f"{fmt_date(r.get('end_date'))}":

                r.get("leave_id")

                for _, r in leaves_df.iterrows()

            }

            selected = st.selectbox(

                "اختر الإجازة",

                list(options.keys())

            )

            leave_id = options[selected]

            row = leaves_df[

                leaves_df["leave_id"] == leave_id

            ].iloc[0]

            new_leave_type = st.selectbox(

                "نوع الإجازة",

                [
                    "سنوية",
                    "مرضية",
                    "بدون راتب",
                    "اضطرارية",
                    "رسمية",
                    "أخرى"
                ],

                index=0

            )

            new_start = st.date_input(

                "من تاريخ",

                value=pd.to_datetime(
                    row["start_date"]
                )

            )

            new_end = st.date_input(

                "إلى تاريخ",

                value=pd.to_datetime(
                    row["end_date"]
                )

            )

            new_notes = st.text_area(

                "ملاحظات",

                value=safe_str(
                    row.get("notes")
                )

            )

            c1, c2 = st.columns(2)

            # =====================================
            # حفظ التعديل
            # =====================================

            with c1:

                if st.button("💾 حفظ التعديل"):

                    from database import update_leave

                    update_leave(

                        leave_id,

                        {

                            "leave_type":
                                new_leave_type,

                            "start_date":
                                pd.Timestamp(
                                    new_start
                                ),

                            "end_date":
                                pd.Timestamp(
                                    new_end
                                ),

                            "notes":
                                new_notes,

                            "status":
                                "معتمدة",

                        }

                    )

                    st.success(
                        "✅ تم تعديل الإجازة"
                    )

                    st.rerun()

            # =====================================
            # حذف
            # =====================================

            with c2:

                if st.button("🗑️ حذف الإجازة"):

                    delete_leave(leave_id)

                    st.success(
                        "✅ تم حذف الإجازة"
                    )

                    st.rerun()







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

            # =====================================================
            # نفس البيانات المعروضة على الشاشة فقط
            # =====================================================
            
            late_emp_pdf = late_emp.copy()
            
            schedule_name = safe_str(
                emp.get("schedule", "")
            )
            
            # =========================================
            # حذف السبت لغير السعوديين
            # =========================================
            
            if (
                "جمعة فقط" in schedule_name
                or
                "الجمعة فقط" in schedule_name
            ):
            
                late_emp_pdf = late_emp_pdf[
            
                    late_emp_pdf["weekday"] != "Saturday"
            
                ].copy()
            
            # =========================================
            # حذف الصفوف الفارغة
            # =========================================
                        
            # =========================================
            # إنشاء الأعمدة الناقصة
            # =========================================
            
            for c in [
            
                "late_minutes",
                "early_leave_minutes",
                "overtime_minutes"
            
            ]:
            
                if c not in late_emp_pdf.columns:
            
                    late_emp_pdf[c] = 0
            
            # =========================================
            # الاحتفاظ فقط بما يظهر في الشاشة
            # =========================================
            
            late_emp_pdf = late_emp_pdf[
            
                (
                    late_emp_pdf["late_minutes"].fillna(0) > 0
                )
            
                |
            
                (
                    late_emp_pdf["early_leave_minutes"].fillna(0) > 0
                )
            
                |
            
                (
                    late_emp_pdf["overtime_minutes"].fillna(0) > 0
                )
            
            ].copy()
            pdf_ar = build_pdf(
                emp,
                late_emp_pdf,
                abs_emp,
                leave_emp,
                lang="ar"
            )
            
            pdf_en = build_pdf(
                emp,
                late_emp_pdf,
                abs_emp,
                leave_emp,
                lang="en"
            )

            st.session_state["pdf_bytes_ar"] = pdf_ar
            st.session_state["pdf_bytes_en"] = pdf_en
            base_name = sanitize_filename(name_ar or name_en)
            base_no = sanitize_filename(emp_no)
            st.session_state["pdf_filename_ar"] = f"{base_name}_{base_no}_AR.pdf"
            st.session_state["pdf_filename_en"] = f"{base_name}_{base_no}_EN.pdf"

            title = month_year_title(emp)
            schedule = safe_str(emp.get("schedule", ""))
            sat_note = (
                "✅ دوام السبت"
                if (
                    "جمعة فقط" in schedule
                    or
                    "الجمعة فقط" in schedule
                )
                else
                "🛑 إجازة السبت"
            )
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
