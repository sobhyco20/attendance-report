# =========================
# core.py — ثوابت ودوال مساعدة مشتركة (تنسيق، تواريخ، ملخصات، ربط الأعذار)
# =========================
import os
import re

import pandas as pd

import arabic_reshaper
from bidi.algorithm import get_display

# مسارات الملفات
EMP_PATH = os.path.join("data", "employees.xlsx")
FONT_PATH = os.path.join("fonts", "Amiri-Regular.ttf")
LOGO_PATH = os.path.join("assets", "logo.png")
SIDE_IMAGE_PATH = os.path.join("assets", "222003582.jpg")
LEAVES_PATH = os.path.join("data", "leaves.xlsx")
ABSENCES_PATH = os.path.join("data", "absences.xlsx")
ATTACHMENTS_DIR = os.path.join("data", "attachments")
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

LEAVE_TYPES = ["سنوية", "مرضية", "بدون راتب", "اضطرارية", "رسمية", "أخرى"]

ABSENCE_TYPES = [
    "غياب بإذن",
    "غياب بدون إذن",
    "تأخير بعذر",
    "خروج مبكر بإذن",
    "أخرى",
]
# الأنواع اللي بتخص أيام الغياب، والأنواع اللي بتخص التأخير/الخروج المبكر
ABSENCE_REASONS = [
    "مراجعة مستشفى / موعد طبي",
    "ظرف عائلي",
    "ظرف طارئ",
    "زحمة طريق / تأخر مواصلات",
    "عطل في السيارة",
    "مهمة عمل خارجية",
    "مراجعة جهة حكومية",
    "مراجعة مدرسة الأبناء",
    "سفر",
    "بدون سبب",
]
ABSENCE_DAY_TYPES = {"غياب بإذن", "غياب بدون إذن"}
LATE_TYPES = {"تأخير بعذر", "خروج مبكر بإذن"}

ABSENCE_COLUMNS = [
    "record_id", "employee_id", "employee_no", "name_ar", "department",
    "record_type", "start_date", "end_date", "reason",
    "attachment_name", "attachment_path", "created_at", "created_by",
]


_PDF_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # إيموجي ورموز مصورة (📅 📄 👥 🔴 🟡 🟢 🚫 🏖 🕋 🚪 ...)
    "\U00002600-\U000027BF"  # رموز متنوعة وDingbats (✅ ❌ ⚠ ☀ ...)
    "\U00002300-\U000023FF"  # رموز تقنية متنوعة (⏱ ⏰ ⌚ ...)
    "\U00002190-\U000021FF"  # أسهم (↩ ➡ ...)
    "\U00002B00-\U00002BFF"  # أسهم ورموز متنوعة إضافية (⬆ ⭐ ...)
    "\U0000FE0F"             # Variation Selector (عرض الإيموجي الملوّن)
    "\U0000200D"             # Zero Width Joiner
    "]+",
    flags=re.UNICODE,
)


def ar(text: str) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    if not s:
        return ""
    s = _PDF_EMOJI_PATTERN.sub("", s)
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    if not s:
        return ""
    return get_display(arabic_reshaper.reshape(s))


def t(ar_text: str, en_text: str, lang: str) -> str:
    return ar_text if lang == "ar" else en_text


def safe_str(x):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()


def fmt_id(x):
    """يحول أي قيمة رقم وظيفي/رقم موظف (بما فيها float زي 27164.0) لنص بدون فواصل عشرية."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return s
    except (ValueError, TypeError):
        return s


def _first_nonempty(series):
    """يرجّع أول قيمة نصية غير فاضية في مجموعة (Series)، وإلا نص فاضي.
    مستخدمة عشان نختار اسم/إدارة تمثيلية للموظف بعد التجميع حسب الرقم
    الوظيفي فقط، من غير ما نضطر ندخل الاسم نفسه في مفتاح التجميع (لو فيه
    أكتر من صيغة كتابة لاسم نفس الموظف زي "أحمد"/"احمد")."""
    for v in series:
        v = safe_str(v)
        if v:
            return v
    return ""


def fmt_date(d):
    try:
        return pd.to_datetime(d).strftime("%d-%m-%Y")
    except Exception:
        return safe_str(d)


def leave_days_count(start_date, end_date) -> int:
    """عدد أيام الإجازة (شامل يوم البداية والنهاية). يرجع 0 لو التواريخ غير صالحة."""
    s = pd.to_datetime(start_date, errors="coerce")
    e = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(s) or pd.isna(e):
        return 0
    return max(int((e - s).days) + 1, 0)


def eid_al_adha_hint() -> str:
    return (
        f"🕋 ملاحظة: إجازة عيد الأضحى المبارك من "
        f"{fmt_date(EID_AL_ADHA_2026_START)} إلى {fmt_date(EID_AL_ADHA_2026_END)} "
        "ولا تُحتسب ضمن الغياب."
    )


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


EID_AL_ADHA_2026_START = pd.Timestamp("2026-05-26")
EID_AL_ADHA_2026_END = pd.Timestamp("2026-05-30")


def exclude_eid_al_adha_absence(summary_df: pd.DataFrame, absence_df: pd.DataFrame):
    if absence_df is None or absence_df.empty or "date" not in absence_df.columns:
        return summary_df, absence_df

    filtered_absence = absence_df.copy()
    absence_dates = pd.to_datetime(filtered_absence["date"], errors="coerce").dt.normalize()
    eid_mask = absence_dates.between(EID_AL_ADHA_2026_START, EID_AL_ADHA_2026_END)

    if not eid_mask.any():
        return summary_df, absence_df

    filtered_absence = filtered_absence.loc[~eid_mask].copy()

    if summary_df is None or summary_df.empty or "absent_days" not in summary_df.columns:
        return summary_df, filtered_absence

    updated_summary = summary_df.copy()
    if "employee_id" in updated_summary.columns and "employee_id" in filtered_absence.columns:
        counts = (
            filtered_absence.assign(
                employee_id=filtered_absence["employee_id"].astype(str).str.strip()
            )
            .groupby("employee_id")
            .size()
        )
        updated_summary["absent_days"] = (
            updated_summary["employee_id"]
            .astype(str)
            .str.strip()
            .map(counts)
            .fillna(0)
            .astype(int)
        )
    else:
        updated_summary["absent_days"] = len(filtered_absence)

    return updated_summary, filtered_absence


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


def absence_records_for_employee(records: pd.DataFrame, emp_key: str, date_from=None, date_to=None) -> pd.DataFrame:
    """سجلات الغياب/التأخير الخاصة بموظف واحد ضمن فترة (لو محددة)."""
    if records is None or records.empty or not emp_key:
        return pd.DataFrame(columns=ABSENCE_COLUMNS)
    key = str(emp_key).strip()
    x = records[
        (records["employee_id"].astype(str).str.strip() == key) |
        (records["employee_no"].astype(str).str.strip() == key)
    ].copy()
    if date_from is not None:
        x = x[x["end_date"] >= pd.to_datetime(date_from).normalize()]
    if date_to is not None:
        x = x[x["start_date"] <= pd.to_datetime(date_to).normalize()]
    return x.sort_values("start_date")


def _find_record_for_date(emp_records: pd.DataFrame, d, allowed_types: set):
    """يرجّع أول سجل مسجّل يغطي التاريخ d ونوعه ضمن allowed_types."""
    if emp_records is None or emp_records.empty or d is None:
        return None
    dd = pd.to_datetime(d, errors="coerce")
    if pd.isna(dd):
        return None
    dd = dd.normalize()
    hit = emp_records[
        (emp_records["start_date"] <= dd) &
        (emp_records["end_date"] >= dd) &
        (emp_records["record_type"].apply(safe_str).isin(allowed_types))
    ]
    if hit.empty:
        return None
    return hit.iloc[-1]


def annotate_absence_days(abs_emp: pd.DataFrame, emp_records: pd.DataFrame) -> pd.DataFrame:
    """
    يضيف لكل يوم غياب نوعه (بإذن / بدون إذن) والسبب.
    أي يوم غياب مالوش تسجيل يعتبر "غياب بدون إذن (غير مسجل)".
    """
    if abs_emp is None or abs_emp.empty:
        return abs_emp
    out = abs_emp.copy()
    types, reasons = [], []
    for _, r in out.iterrows():
        rec = _find_record_for_date(emp_records, r.get("date"), ABSENCE_DAY_TYPES)
        if rec is None:
            types.append("غياب بدون إذن (غير مسجل)")
            reasons.append("")
        else:
            types.append(safe_str(rec.get("record_type")))
            reasons.append(safe_str(rec.get("reason")))
    out["absence_type"] = types
    out["absence_reason"] = reasons
    return out


def annotate_late_days(late_emp: pd.DataFrame, emp_records: pd.DataFrame) -> pd.DataFrame:
    """يضيف سبب التأخير/الخروج المبكر لو فيه عذر مسجّل لنفس اليوم."""
    if late_emp is None or late_emp.empty:
        return late_emp
    out = late_emp.copy()
    reasons = []
    for _, r in out.iterrows():
        rec = _find_record_for_date(emp_records, r.get("date"), LATE_TYPES | {"أخرى"})
        if rec is None:
            reasons.append("")
        else:
            txt_ = safe_str(rec.get("record_type"))
            if safe_str(rec.get("reason")):
                txt_ += f" — {safe_str(rec.get('reason'))}"
            reasons.append(txt_)
    out["excuse"] = reasons
    return out


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
    emp["employee_id"] = emp["employee_id"].apply(fmt_id)
    emp["employee_no"] = emp["employee_no"].apply(fmt_id)
    # لو الرقم الوظيفي فاضي لصف معين نستخدم الرقم الآخر بدلاً منه،
    # عشان نضمن إن كل موظف له معرف واحد ثابت يُستخدم في كل الشاشات (تسجيل/عرض/تعديل الإجازات)
    blank_id = emp["employee_id"] == ""
    emp.loc[blank_id, "employee_id"] = emp.loc[blank_id, "employee_no"]
    blank_no = emp["employee_no"] == ""
    emp.loc[blank_no, "employee_no"] = emp.loc[blank_no, "employee_id"]
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
    return f"{safe_str(row.get('name_ar'))} — {fmt_id(row.get('employee_no') or row.get('employee_id'))}"


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


SICK_LEAVE_ANNUAL_QUOTA = 30  # عدد أيام الإجازة المرضية المسموح بها سنويًا لكل موظف


def compute_sick_leave_summary(
    leaves_df: pd.DataFrame,
    date_from=None,
    date_to=None,
) -> pd.DataFrame:
    """
    تجميع الإجازات المرضية لكل موظف ضمن فترة محددة: عدد الإجازات، إجمالي الأيام،
    ومؤشر تجاوز الحد السنوي (30 يوم).
    كل يوم إجازة يقع خارج الفترة المحددة يتم استبعاده (قص عند حدود الفترة).
    """
    if leaves_df is None or leaves_df.empty:
        return pd.DataFrame()

    x = leaves_df.copy()
    x["leave_type"] = x["leave_type"].apply(safe_str)
    x = x[x["leave_type"].str.strip() == "مرضية"].copy()
    if x.empty:
        return pd.DataFrame()

    x["start_date"] = pd.to_datetime(x["start_date"], errors="coerce")
    x["end_date"] = pd.to_datetime(x["end_date"], errors="coerce")
    x = x.dropna(subset=["start_date", "end_date"]).copy()
    if x.empty:
        return pd.DataFrame()

    date_from = pd.to_datetime(date_from) if date_from is not None else None
    date_to = pd.to_datetime(date_to) if date_to is not None else None

    if date_from is not None:
        x = x[x["end_date"] >= date_from].copy()
    if date_to is not None:
        x = x[x["start_date"] <= date_to].copy()
    if x.empty:
        return pd.DataFrame()

    # قص كل سجل عند حدود الفترة المحددة قبل احتساب عدد الأيام
    if date_from is not None:
        x["start_date"] = x["start_date"].clip(lower=date_from)
    if date_to is not None:
        x["end_date"] = x["end_date"].clip(upper=date_to)

    x["days_count"] = (x["end_date"] - x["start_date"]).dt.days + 1
    x["days_count"] = x["days_count"].clip(lower=1)

    # 🔥 التجميع حسب الرقم الوظيفي فقط (مش الاسم/الإدارة)، عشان لو اسم نفس
    # الموظف اتسجل بأكتر من صيغة كتابة (زي "أحمد"/"احمد") ما يتحسبش كموظف
    # تاني في الملخص. الاسم والإدارة المعروضين بياخدوا أول قيمة غير فاضية.
    x["employee_id"] = x["employee_id"].apply(fmt_id)
    x["employee_no"] = x["employee_no"].apply(fmt_id)

    grouped = x.groupby(
        ["employee_id", "employee_no"],
        dropna=False,
        as_index=False,
    ).agg(
        name_ar=("name_ar", _first_nonempty),
        department=("department", _first_nonempty),
        leave_count=("leave_id", "count"),
        total_days=("days_count", "sum"),
        last_leave_date=("end_date", "max"),
    )

    def _status(days):
        if days >= SICK_LEAVE_ANNUAL_QUOTA:
            return "🔴 إنذار - تجاوز الحد"
        if days >= SICK_LEAVE_ANNUAL_QUOTA * 0.7:
            return "🟡 اقترب من الحد"
        return "🟢 طبيعي"

    grouped["status"] = grouped["total_days"].apply(_status)
    grouped["remaining_days"] = (SICK_LEAVE_ANNUAL_QUOTA - grouped["total_days"]).clip(lower=0)
    grouped["exceeded_days"] = (grouped["total_days"] - SICK_LEAVE_ANNUAL_QUOTA).clip(lower=0)

    grouped = grouped.sort_values(
        ["total_days", "leave_count"], ascending=[False, False]
    ).reset_index(drop=True)
    grouped.insert(0, "rank", grouped.index + 1)

    return grouped


def compute_all_leave_summary(
    leaves_df: pd.DataFrame,
    date_from=None,
    date_to=None,
) -> pd.DataFrame:
    """
    تجميع كل الإجازات (كل الأنواع) لكل موظف ضمن فترة محددة:
    عدد الإجازات، إجمالي الأيام، وآخر إجازة.
    كل يوم إجازة يقع خارج الفترة المحددة يتم استبعاده (قص عند حدود الفترة).
    """
    if leaves_df is None or leaves_df.empty:
        return pd.DataFrame()

    x = leaves_df.copy()
    x["leave_type"] = x["leave_type"].apply(safe_str)

    x["start_date"] = pd.to_datetime(x["start_date"], errors="coerce")
    x["end_date"] = pd.to_datetime(x["end_date"], errors="coerce")
    x = x.dropna(subset=["start_date", "end_date"]).copy()
    if x.empty:
        return pd.DataFrame()

    date_from = pd.to_datetime(date_from) if date_from is not None else None
    date_to = pd.to_datetime(date_to) if date_to is not None else None

    if date_from is not None:
        x = x[x["end_date"] >= date_from].copy()
    if date_to is not None:
        x = x[x["start_date"] <= date_to].copy()
    if x.empty:
        return pd.DataFrame()

    # قص كل سجل عند حدود الفترة المحددة قبل احتساب عدد الأيام
    if date_from is not None:
        x["start_date"] = x["start_date"].clip(lower=date_from)
    if date_to is not None:
        x["end_date"] = x["end_date"].clip(upper=date_to)

    x["days_count"] = (x["end_date"] - x["start_date"]).dt.days + 1
    x["days_count"] = x["days_count"].clip(lower=1)

    # 🔥 التجميع حسب الرقم الوظيفي فقط (مش الاسم/الإدارة)، عشان لو اسم نفس
    # الموظف اتسجل بأكتر من صيغة كتابة (زي "أحمد"/"احمد") ما يتحسبش كموظف
    # تاني في الملخص. الاسم والإدارة المعروضين بياخدوا أول قيمة غير فاضية.
    x["employee_id"] = x["employee_id"].apply(fmt_id)
    x["employee_no"] = x["employee_no"].apply(fmt_id)

    grouped = x.groupby(
        ["employee_id", "employee_no"],
        dropna=False,
        as_index=False,
    ).agg(
        name_ar=("name_ar", _first_nonempty),
        department=("department", _first_nonempty),
        leave_count=("leave_id", "count"),
        total_days=("days_count", "sum"),
        last_leave_date=("end_date", "max"),
    )

    # نوع آخر إجازة لكل موظف (بعد ترتيب السجلات بالتاريخ)
    last_type_df = (
        x.sort_values("end_date")
        .groupby(["employee_id", "employee_no"], dropna=False)
        .tail(1)[["employee_id", "employee_no", "leave_type"]]
        .rename(columns={"leave_type": "آخر_نوع_إجازة"})
    )
    grouped = grouped.merge(
        last_type_df, on=["employee_id", "employee_no"], how="left"
    )

    # عدد أيام كل نوع إجازة على حدة (سنوية / مرضية / بدون راتب / ...) لكل موظف
    by_type = (
        x.groupby(["employee_id", "employee_no", "leave_type"], dropna=False)["days_count"]
        .sum()
        .reset_index()
    )
    breakdown_map = {}
    for (eid, eno), g in by_type.groupby(["employee_id", "employee_no"]):
        parts = [f"{safe_str(t)}: {int(d)}" for t, d in zip(g["leave_type"], g["days_count"])]
        breakdown_map[(eid, eno)] = " | ".join(parts)

    grouped["نوع_الإجازات_تفصيلي"] = grouped.apply(
        lambda r: breakdown_map.get((r["employee_id"], r["employee_no"]), ""),
        axis=1,
    )

    grouped = grouped.sort_values(
        ["total_days", "leave_count"], ascending=[False, False]
    ).reset_index(drop=True)
    grouped.insert(0, "rank", grouped.index + 1)

    return grouped
