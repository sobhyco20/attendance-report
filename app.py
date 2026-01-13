import os
import re
from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st

from attendance_engine import process_attendance

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
# إعدادات الصفحة (لازم أول شيء)
# =========================
st.set_page_config(page_title="Attendance Report", layout="wide")


# =========================
# Cookies
# =========================
cookies = EncryptedCookieManager(prefix="attendance_app", password="super-secret-password-change-me")
if not cookies.ready():
    st.stop()


# =========================
# Session State Init (مهم)
# =========================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "login_user" not in st.session_state:
    st.session_state["login_user"] = ""


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


def require_login(app_name=" التأخير والغياب"):
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
# مسارات
# =========================
EMP_PATH = os.path.join("data", "employees.xlsx")
FONT_PATH = os.path.join("fonts", "Amiri-Regular.ttf")
LOGO_PATH = os.path.join("assets", "logo.png")
SIDE_IMAGE_PATH = os.path.join("assets", "222003582.jpg")


# =========================
# CSS
# =========================
st.markdown(
    """
<style>
section[data-testid="stSidebar"]{
  min-width: 380px !important;
  width: 380px !important;
}
section[data-testid="stSidebar"] > div{
  width: 380px !important;
}

:root {
  --bg: #F8FAFC;
  --card: #FFFFFF;
  --card-soft: #F1F5F9;
  --border: #E2E8F0;

  --text: #0F172A;
  --muted: #64748B;

  --primary: #4F46E5;
  --success: #10B981;
  --warning: #F59E0B;
  --danger: #EF4444;

  --badge: #EEF2FF;
  --shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0B0F1A;
    --card: #151B2C;
    --card-soft: #1E2638;
    --border: #2D364D;

    --text: #F1F5F9;
    --muted: #94A3B8;

    --primary: #818CF8;
    --success: #34D399;
    --warning: #FBBF24;
    --danger: #FB7185;

    --badge: #1E293B;
    --shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  }
}

* { transition: background-color 0.3s ease, border-color 0.3s ease; }

.block-container { max-width: 1080px; padding-top: 2rem; }

html, body, [class*="css"] {
  direction: rtl;
  color: var(--text);
  font-family: "Segoe UI", "Tahoma", system-ui;
}

.stApp {
  background-color: var(--bg);
  background-image: radial-gradient(at 0% 0%, rgba(79, 70, 229, 0.03) 0px, transparent 50%),
                    radial-gradient(at 100% 100%, rgba(79, 70, 229, 0.03) 0px, transparent 50%);
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  box-shadow: var(--shadow);
  margin-bottom: 16px;
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
}

.kpi {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  text-align: center;
  box-shadow: var(--shadow);
}

.kpi .v {
  font-size: 28px;
  font-weight: 800;
  color: var(--primary);
  display: block;
}

.kpi .l {
  font-size: 14px;
  color: var(--muted);
  font-weight: 500;
  margin-top: 4px;
}

.card-title {
  display: block;
  width: 100%;
  box-sizing: border-box;
  margin: 0 0 12px 0;
  padding: 8px 12px;
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
  background: linear-gradient(90deg, rgba(79,70,229,0.12), rgba(79,70,229,0.02));
  border-radius: 10px;
}

.list-item {
  background: var(--card-soft);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 8px;
}

.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 11px;
  background: var(--badge);
  color: var(--primary);
  font-weight: 700;
  text-transform: uppercase;
}

h1, h2, h3 { color: var(--text); margin-bottom: 1rem; }

section[data-testid="stSidebar"] {
  background-color: var(--card);
  border-left: 1px solid var(--border);
}

.ok { color: var(--success); }
.warn { color: var(--warning); }
.err { color: var(--danger); }
.muted { color: var(--muted); }

/* Export Buttons */
.export-box div[data-testid="stDownloadButton"]:nth-of-type(1) button {
  background: #10B981 !important;
  border: 1px solid #10B981 !important;
  color: white !important;
  font-weight: 800 !important;
  border-radius: 12px !important;
}
.export-box div[data-testid="stDownloadButton"]:nth-of-type(2) button {
  background: #2563EB !important;
  border: 1px solid #2563EB !important;
  color: white !important;
  font-weight: 800 !important;
  border-radius: 12px !important;
}

/* Net Box */
.net-box{
  border: 2px solid var(--border);
  background: linear-gradient(90deg, rgba(79,70,229,0.10), rgba(79,70,229,0.02));
  border-radius: 18px;
  padding: 18px 18px;
  box-shadow: var(--shadow);
  margin: 14px 0 18px 0;
}
.net-title{ font-weight: 900; font-size: 18px; margin-bottom: 10px; }
.net-big{ font-weight: 1000; font-size: 44px; line-height: 1.1; }
.net-sub{ margin-top: 6px; font-size: 14px; color: var(--muted); font-weight: 700; }
.net-good{ color: var(--success); }
.net-bad{ color: var(--danger); }
.net-mid{ color: var(--warning); }
.net-row{ display:flex; gap:14px; flex-wrap: wrap; margin-top: 12px; }
.net-pill{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
  font-weight: 900;
  min-width: 200px;
}
.net-pill span{ display:block; font-size: 12px; color: var(--muted); font-weight: 700; margin-top: 2px; }

</style>
""",
    unsafe_allow_html=True,
)


# =========================
# Login
# =========================
require_login("تقرير التأخير والغياب")


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


def build_pdf(emp_row, late_emp: pd.DataFrame, abs_emp: pd.DataFrame, lang: str = "ar") -> bytes:
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

    h_style = ParagraphStyle("h", parent=styles["Heading3"], fontName=font_main, fontSize=12, alignment=align_head, spaceAfter=6)
    p_style = ParagraphStyle("p", parent=styles["BodyText"], fontName=font_main, fontSize=10.5, alignment=align_text, leading=15)
    total_style = ParagraphStyle("total", parent=p_style, fontName=font_main, fontSize=13.0, alignment=align_text, leading=18)

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
            note = "📝 ملاحظة: تم احتساب التأخير والإضافي بناءً على إجمالي ساعات العمل اليومية (9 ساعات) من أول بصمة دخول إلى آخر بصمة خروج."
            story.append(Paragraph(ar(note), note_style))
        else:
            note = "📝 Note: This employee is calculated by daily work hours (9 hours) from first punch-in to last punch-out."
            story.append(Paragraph(note, note_style))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.lightgrey))
    story.append(Spacer(1, 8))

    # =========================
    # Late / Daily Hours
    # =========================
    late_title = "التأخير والإضافي" if (attendance_rule == "daily_hours" and lang == "ar") else t("التأخير", "Late Attendance", lang)
    story.append(Paragraph(txt(late_title), h_style))

    if late_emp is None or late_emp.empty:
        story.append(Paragraph(txt(t("لا يوجد بيانات", "No records", lang)), p_style))
    else:
        le = late_emp.copy()
        if "date" in le.columns:
            le = le.sort_values("date")
            le["date"] = le["date"].apply(fmt_date)

        if attendance_rule == "daily_hours":
            # جدول المستثنين (First/Last + Worked + Deficit + Overtime)
            if "worked_minutes" not in le.columns:
                le["worked_minutes"] = 0
            if "overtime_minutes" not in le.columns:
                le["overtime_minutes"] = 0

            rows = [rtl_row([
                txt(t("اليوم", "Day", lang)),
                txt(t("التاريخ", "Date", lang)),
                txt(t("أول بصمة", "First In", lang)),
                txt(t("آخر بصمة", "Last Out", lang)),
                txt(t("ساعات العمل", "Worked", lang)),
                txt(t("تأخير", "Deficit", lang)),
                txt(t("الإضافي", "Overtime", lang)),
            ])]

            for _, r in le.iterrows():
                day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
                first_in = fmt_time(r.get("first_punch_time", ""))
                last_out = fmt_time(r.get("last_punch_time", ""))

                worked = mm_to_hhmm(int(r.get("worked_minutes", 0) or 0))
                deficit = mm_to_hhmm(int(r.get("late_minutes", 0) or 0))
                overtime = mm_to_hhmm(int(r.get("overtime_minutes", 0) or 0))

                row = [
                    txt(day_val),
                    txt(safe_str(r.get("date", ""))),
                    txt(first_in),
                    txt(last_out),
                    txt(worked),
                    txt(deficit),
                    txt(overtime),
                ]
                rows.append(rtl_row(row))

            widths = rtl_cols([2.6*cm, 3.2*cm, 2.6*cm, 2.6*cm, 3.0*cm, 2.6*cm, 2.6*cm])
            t1 = Table(rows, colWidths=widths)
            t1.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font_main),
                ("FONTSIZE", (0, 0), (-1, 0), 10.5),
                ("FONTSIZE", (0, 1), (-1, -1), 9.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t1)
            story.append(Spacer(1, 8))

            # ✅ إجماليات: التأخير + التعويض في نفس السطر + الصافي بسطر منفصل
            total_deficit = int(emp_row.get("total_late_minutes", 0) or 0)
            total_overtime = int(emp_row.get("total_overtime_minutes", 0) or 0)

            # fallback لو summary لا يحتوي total_overtime_minutes
            if total_overtime == 0 and "overtime_minutes" in le.columns:
                total_overtime = int(le["overtime_minutes"].sum())

            net_minutes = total_overtime - total_deficit

            def to_hm(m: int):
                m = int(m or 0)
                h = abs(m) // 60
                mm = abs(m) % 60
                return h, mm

            d_h, d_m = to_hm(total_deficit)
            o_h, o_m = to_hm(total_overtime)
            n_h, n_m = to_hm(net_minutes)

            if lang == "ar":
                # سطر واحد: التأخير - التعويض
                line1 = f"⏱ إجمالي التأخير: {d_h} ساعة و {d_m} دقيقة  -  إجمالي التعويض/الإضافي: {o_h} ساعة و {o_m} دقيقة"
                story.append(Paragraph(ar(line1), total_style))

                # سطر منفصل: الصافي
                if net_minutes > 0:
                    line2 = f"✅ الصافي: إضافي {n_h} ساعة و {n_m} دقيقة"
                elif net_minutes < 0:
                    line2 = f"❌ الصافي: تأخير {n_h} ساعة و {n_m} دقيقة"
                else:
                    line2 = "➖ الصافي: متعادل (0 دقيقة)"
                story.append(Paragraph(ar(line2), total_style))

            else:
                line1 = f"⏱ Total Deficit: {d_h}h {d_m}m  -  Total Overtime: {o_h}h {o_m}m"
                story.append(Paragraph(line1, total_style))

                if net_minutes > 0:
                    line2 = f"✅ Net: Overtime {n_h}h {n_m}m"
                elif net_minutes < 0:
                    line2 = f"❌ Net: Deficit {n_h}h {n_m}m"
                else:
                    line2 = "➖ Net: Balanced (0m)"
                story.append(Paragraph(line2, total_style))

        else:
            # جدول الموظف العادي RTL بالعربي
            rows = [rtl_row([
                txt(t("اليوم", "Day", lang)),
                txt(t("التاريخ", "Date", lang)),
                txt(t("أول بصمة", "First Punch", lang)),
                txt(t("الدقائق", "Minutes", lang)),
            ])]

            for _, r in le.iterrows():
                day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
                row = [
                    txt(day_val),
                    txt(safe_str(r.get("date", ""))),
                    txt(fmt_time(r.get("first_punch_time", ""))),
                    txt(str(int(r.get("late_minutes", 0) or 0))),
                ]
                rows.append(rtl_row(row))

            t1 = Table(rows, colWidths=rtl_cols([4.0 * cm, 5.0 * cm, 3.5 * cm, 3.0 * cm]))
            t1.setStyle(TableStyle([
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
            story.append(t1)
            story.append(Spacer(1, 6))

            total_late = int(emp_row.get("total_late_minutes", 0) or 0)
            if lang == "ar":
                story.append(Paragraph(ar(f"⏱ إجمالي التأخير: {mm_to_hhmm(total_late)}"), total_style))
            else:
                story.append(Paragraph(f"⏱ Total Late: {mm_to_hhmm(total_late)}", total_style))

    story.append(Spacer(1, 12))

    # =========================
    # Absence (RTL بالعربي)
    # =========================
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

    doc.build(story, onFirstPage=on_first_page)
    return buf.getvalue()


# =========================
# تشغيل المعالجة
# =========================
employees_df = load_employees_silent()

with st.sidebar:
    st.header("⚙️ الإعدادات")
    st.markdown("### 👤 المستخدم")
    st.success(f"✅ {st.session_state.get('login_user','')}")

    uploaded_file = st.file_uploader("📄 ارفع ملف البصمة (Excel)", type=["xlsx", "xls"], key="att_file")
    start_time = st.time_input("🕗 وقت بداية الدوام", value=pd.to_datetime("08:00").time(), key="start_time")
    grace = st.number_input("⏱ دقائق السماح", min_value=0, max_value=120, value=15, key="grace")
    st.caption("ℹ️ يتم استخراج التقرير تلقائيًا بمجرد رفع الملف.")

if not uploaded_file:
    st.info("ارفع ملف البصمة من القائمة الجانبية لعرض التقرير.")
    st.stop()

summary, late, absence, exempt_report = process_attendance(
    uploaded_file,
    start_time=start_time.strftime("%H:%M"),
    grace_minutes=int(grace),
    schedule_mode="by_nationality",
    employees_df=employees_df,
    daily_required_hours=9.0,
)

if summary is None or summary.empty:
    st.error("لا توجد بيانات بعد المعالجة.")
    st.stop()

if len(summary) != 1:
    st.warning("الملف يحتوي أكثر من موظف — هذا العرض مصمم لموظف واحد حاليًا.")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.stop()

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
exempt_emp = exempt_report[exempt_report["employee_id"].astype(str).str.strip() == emp_personnel_id].copy() if exempt_report is not None and not exempt_report.empty else pd.DataFrame()

if not late_emp.empty and "weekday" in late_emp.columns:
    late_emp["weekday_ar"] = late_emp["weekday"].apply(weekday_to_ar)
if not abs_emp.empty and "weekday" in abs_emp.columns:
    abs_emp["weekday_ar"] = abs_emp["weekday"].apply(weekday_to_ar)

pdf_ar = build_pdf(emp, late_emp, abs_emp, lang="ar")
pdf_en = build_pdf(emp, late_emp, abs_emp, lang="en")

st.session_state["pdf_bytes_ar"] = pdf_ar
st.session_state["pdf_bytes_en"] = pdf_en

base_name = sanitize_filename(name_ar or name_en)
base_no = sanitize_filename(emp_no)
st.session_state["pdf_filename_ar"] = f"{base_name}_{base_no}_AR.pdf"
st.session_state["pdf_filename_en"] = f"{base_name}_{base_no}_EN.pdf"

# =========================
# عرض الشاشة
# =========================
st.title("")
title = month_year_title(emp)
schedule = safe_str(emp.get("schedule", ""))

sat_note = "✅ دوام السبت" if schedule == "جمعة فقط" else "🛑 إجازة السبت"
fri_note = "🛑 إجازة الجمعة"
st.caption(f"{fri_note} • {sat_note}")
st.markdown(
    f"""
<div class="card">
  <div class="card-title">{title}</div>
  <div style="font-size:26px;font-weight:900;margin-bottom:2px">👤 {name_ar}</div>
  <div class="muted">{name_en}</div>
  <div class="muted" style="margin-top:2px">{nat}</div>
  <div style="margin-top:10px;font-weight:800">الكود / الرقم الوظيفي: {emp_no}</div>
  <div class="muted" style="margin-top:2px">{job}</div>
  <div class="muted" style="margin-top:2px">🏢 {dept}</div>
</div>
""",
    unsafe_allow_html=True,
)

k1, k2, k3 = st.columns(3)
k1.markdown(
    f'<div class="kpi"><div class="v">{int(emp.get("total_late_minutes",0) or 0)}</div><div class="l">إجمالي دقائق التأخير</div></div>',
    unsafe_allow_html=True,
)
k2.markdown(
    f'<div class="kpi"><div class="v">{int(emp.get("late_days",0) or 0)}</div><div class="l">عدد أيام التأخير</div></div>',
    unsafe_allow_html=True,
)
k3.markdown(
    f'<div class="kpi"><div class="v">{int(emp.get("absent_days",0) or 0)}</div><div class="l">عدد أيام الغياب</div></div>',
    unsafe_allow_html=True,
)

attendance_rule = safe_str(emp.get("attendance_calculation", "")).strip().lower()

if attendance_rule == "daily_hours":
    total_deficit = int(emp.get("total_late_minutes", 0) or 0)
    total_overtime = int(emp.get("total_overtime_minutes", 0) or 0)
    net = total_overtime - total_deficit

    if net > 0:
        net_label = "صافي إضافي"
        net_class = "net-good"
    elif net < 0:
        net_label = "صافي تأخير"
        net_class = "net-bad"
    else:
        net_label = "متعادل"
        net_class = "net-mid"

    st.markdown(
        f"""
        <div class="net-box">
          <div class="net-title">🧾 نتيجة الاحتساب (مستثنى: 9 ساعات يوميًا)</div>
          <div class="net-big {net_class}">{net_label}: {mm_to_hhmm(net)}</div>
          <div class="net-sub">الصافي = إجمالي الإضافي − إجمالي التأخير</div>

          <div class="net-row">
            <div class="net-pill">
              ⬇️ إجمالي التأخير: <b>{mm_to_hhmm(total_deficit)}</b>
              <span>(أيام أقل من 9 ساعات)</span>
            </div>
            <div class="net-pill">
              ⬆️ إجمالي التعويض/الإضافي: <b>{mm_to_hhmm(total_overtime)}</b>
              <span>(أيام أكثر من 9 ساعات)</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)


st.markdown("<br>", unsafe_allow_html=True)

right, left = st.columns(2, gap="large")

# =========================
# ✅ شاشة المستثنين: عرض فقط الأيام التي بها عجز أو إضافي
# =========================
with right:
    title_box = "⏱ التأخير / التعويض (مستثنى)" if attendance_rule == "daily_hours" else "⏱ التأخير"
    st.markdown(f'<div class="card"><div class="card-title">{title_box}</div>', unsafe_allow_html=True)

    if attendance_rule == "daily_hours":
        if exempt_emp is None or exempt_emp.empty:
            st.success("لا يوجد عجز أو تعويض ✅")
        else:
            # ترتيب حسب التاريخ
            exempt_emp = exempt_emp.copy()
            exempt_emp["date"] = pd.to_datetime(exempt_emp["date"], errors="coerce")
            exempt_emp = exempt_emp.sort_values("date")

            # عرض كعناصر جميلة
            for _, r in exempt_emp.iterrows():
                day = safe_str(r.get("weekday_ar", ""))
                d = fmt_date(r.get("date"))
                fi = safe_str(r.get("first_in", ""))
                lo = safe_str(r.get("last_out", ""))

                try:
                    fi_str = pd.to_datetime(str(fi), errors="coerce").strftime("%H:%M") if str(fi) not in ["", "NaT"] else ""
                except Exception:
                    fi_str = ""
                try:
                    lo_str = pd.to_datetime(str(lo), errors="coerce").strftime("%H:%M") if str(lo) not in ["", "NaT"] else ""
                except Exception:
                    lo_str = ""

                worked = mm_to_hhmm(int(r.get("worked_minutes", 0) or 0))
                deficit = int(r.get("deficit_minutes", 0) or 0)
                overtime = int(r.get("overtime_minutes", 0) or 0)

                # نص الحالة
                parts = []
                if deficit > 0:
                    parts.append(f"<b class='err'>عجز/تأخير: {mm_to_hhmm(deficit)}</b>")
                if overtime > 0:
                    parts.append(f"<b class='ok'>تعويض/إضافي: {mm_to_hhmm(overtime)}</b>")
                status_html = " • ".join(parts) if parts else "<b class='muted'>—</b>"

                st.markdown(
                    f"""
                    <div class="list-item">
                        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
                            <div>
                                <span class="badge">{day}</span>
                                <span class="muted"> {d}</span>
                            </div>
                            <div style="font-weight:900">{status_html}</div>
                        </div>
                        <div class="muted" style="margin-top:6px">
                            أول بصمة: <b>{fi_str}</b> — آخر بصمة: <b>{lo_str}</b>
                            <span style="margin:0 10px">|</span>
                            ساعات العمل: <b>{worked}</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        if late_emp.empty:
            st.success("لا يوجد تأخير ✅")
        else:
            late_emp = late_emp.sort_values("date") if "date" in late_emp.columns else late_emp
            for _, r in late_emp.iterrows():
                fp = r.get("first_punch_time", "")
                try:
                    fp_str = pd.to_datetime(str(fp), errors="coerce").strftime("%H:%M") if str(fp) not in ["", "NaT"] else ""
                except Exception:
                    fp_str = ""

                st.markdown(
                    f"""
                    <div class="list-item">
                        <b class="warn">{int(r.get('late_minutes',0) or 0)} دقيقة</b>
                        <span class="muted"> — أول بصمة {fp_str}</span><br>
                        <span>{fmt_date(r.get('date'))}</span>
                        <span class="badge">{safe_str(r.get('weekday_ar',''))}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("</div>", unsafe_allow_html=True)

with left:
    st.markdown('<div class="card"><div class="card-title">🚫 الغياب</div>', unsafe_allow_html=True)

    if abs_emp.empty:
        st.success("لا يوجد غياب ✅")
    else:
        abs_emp = abs_emp.sort_values("date") if "date" in abs_emp.columns else abs_emp
        for _, r in abs_emp.iterrows():
            st.markdown(
                f"""
                <div class="list-item">
                    <b class="err">غياب</b> — {fmt_date(r.get('date'))}
                    <span class="badge">{safe_str(r.get('weekday_ar',''))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# PDF Download + Logout (في sidebar)
# =========================
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
