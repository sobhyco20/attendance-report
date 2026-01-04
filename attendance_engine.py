import re
import pandas as pd
import datetime as dt

WEEKDAY_AR = {
    "Monday": "الاثنين",
    "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء",
    "Thursday": "الخميس",
    "Friday": "الجمعة",
    "Saturday": "السبت",
    "Sunday": "الأحد",
}

def weekday_ar(day) -> str:
    if day is None or (isinstance(day, float) and pd.isna(day)):
        return ""
    s = str(day).strip()
    return WEEKDAY_AR.get(s, s)


def _find_header_row(raw: pd.DataFrame, max_scan_rows: int = 30) -> int:
    """
    يبحث عن صف يحتوي على عناوين أعمدة معروفة مثل Employee ID و Date
    """
    targets = {"employee id", "date"}
    for i in range(min(max_scan_rows, len(raw))):
        row = raw.iloc[i].astype(str).str.strip().str.lower().tolist()
        if targets.issubset(set(row)):
            return i
    return 0  # fallback


def _read_attendance_any_format(file) -> pd.DataFrame:
    """
    يقرأ ملف البصمة حتى لو كان فيه سطور عنوان قبل الهيدر الحقيقي.
    """
    raw = pd.read_excel(file, header=None)
    hdr = _find_header_row(raw)

    columns = raw.iloc[hdr].tolist()
    df = raw.iloc[hdr + 1 :].copy()
    df.columns = columns

    # حذف صفوف فاضية بالكامل
    df = df.dropna(how="all")
    return df


def _is_saudi(nat) -> bool:
    # ✅ الافتراضي سعودي إذا لا توجد جنسية
    if nat is None or (isinstance(nat, float) and pd.isna(nat)):
        return True

    s = str(nat).strip().lower()
    if not s:
        return True

    s = re.sub(r"\s+", " ", s)

    keys = [
        # عربي
        "سعود", "سعودي", "سعودية", "السعودية", "السعوديه",
        "المملكة العربية السعودية", "المملكه العربيه السعوديه",
        # إنجليزي
        "saudi", "saudi arabia", "kingdom of saudi arabia",
        "ksa", "k.s.a", "k s a",
    ]
    return any(k in s for k in keys)


def process_attendance(
    attendance_file,
    start_time="08:00",
    grace_minutes=15,
    schedule_mode="by_nationality",  # by_nationality | auto | fri | fri_sat
    employees_df: pd.DataFrame | None = None,
):
    # 1) قراءة البصمة
    df = _read_attendance_any_format(attendance_file)

    # 2) rename لملف البصمة
    df = df.rename(
        columns={
            "Employee ID": "employee_id",
            "First Name": "name_att",
            "Department": "department_att",
            "Date": "date",
            "Weekday": "weekday_raw",
            "First Punch": "first_punch",
            "Last Punch": "last_punch",
        }
    )

    if "employee_id" not in df.columns or "date" not in df.columns:
        raise KeyError(f"Attendance missing required columns. Available: {list(df.columns)}")

    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["weekday"] = df["date"].dt.day_name()
    df["weekday_ar"] = df["weekday"].map(WEEKDAY_AR).fillna(df["weekday"])

    fp = pd.to_datetime(df.get("first_punch"), errors="coerce")
    df["first_punch_time"] = fp.dt.time

    # 3) دمج بيانات الموظفين (إن وُجدت)
    if employees_df is not None and not employees_df.empty:
        emp = employees_df.copy()

        emp = emp.rename(
            columns={
                "Personnel Number": "employee_id",
                "Employee ID": "employee_id",
                "Emp ID": "employee_id",
                "ID": "employee_id",

                "Arabic name": "name_ar",
                "Search name": "name_en",
                "emp_name": "name_ar",

                "Contrac Profession": "job_title",

                "nationality": "nationality",
                "Nationality": "nationality",
                "الجنسية": "nationality",

                "Section | Department": "department_emp",

                "Employee No": "employee_no",
                "الرقم الوظيفي": "employee_no",
            }
        )

        if "employee_no" not in emp.columns:
            emp["employee_no"] = emp["employee_id"]

        df["employee_id"] = df["employee_id"].astype(str).str.strip()
        emp["employee_id"] = emp["employee_id"].astype(str).str.strip()

        keep_cols = ["employee_id"]
        for c in ["name_ar", "name_en", "job_title", "nationality", "employee_no", "department_emp"]:
            if c in emp.columns:
                keep_cols.append(c)

        df = df.merge(emp[keep_cols], on="employee_id", how="left")

    # 4) إعدادات الوقت
    hh, mm = start_time.split(":")
    start_td = dt.timedelta(hours=int(hh), minutes=int(mm))
    late_limit = start_td + dt.timedelta(minutes=int(grace_minutes))

    results, late_details, absence_details = [], [], []

    def pick_first(series, fallback=""):
        if series is None:
            return fallback
        s = series.dropna()
        return s.iloc[0] if len(s) else fallback

    # تحويل وقت البصمة لـ timedelta
    def time_to_td(t):
        if pd.isna(t):
            return None
        return dt.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)

    for emp_id, emp_df in df.groupby("employee_id", dropna=False):
        emp_df = emp_df.copy()

        name_ar = pick_first(emp_df.get("name_ar"), pick_first(emp_df.get("name_att"), ""))
        name_en = pick_first(emp_df.get("name_en"), "")
        emp_dept = pick_first(emp_df.get("department_emp"), pick_first(emp_df.get("department_att"), ""))
        emp_job  = pick_first(emp_df.get("job_title"), "")
        emp_nat  = pick_first(emp_df.get("nationality"), "")
        emp_no   = pick_first(emp_df.get("employee_no"), emp_id)

        is_saudi = _is_saudi(emp_nat)

        # =========================
        # ✅ قاعدة السبت الجديدة
        # - السعودي: السبت إجازة دائمًا
        # - غير السعودي: السبت يُحسب (دوام/غياب) فقط إذا كان يحضر السبت فعليًا
        # =========================
        # هل لديه أي حضور يوم سبت (أي سجل يوم Saturday)؟
        # (ممكن تشددها لو تحب: وجود first_punch_time)
        has_sat_presence = (emp_df["weekday"] == "Saturday").any()

        # هل السبت يوم عمل لهذا الموظف؟
        saturday_is_workday = (not is_saudi) and has_sat_presence

        # جدول/وصف للعرض في التقارير
        # "جمعة فقط" = السبت دوام
        # "جمعة وسبت" = السبت إجازة
        schedule = "جمعة فقط" if saturday_is_workday else "جمعة وسبت"

        def is_workday(day_name: str) -> bool:
            # الجمعة إجازة للجميع
            if day_name == "Friday":
                return False
            # السبت حسب القاعدة أعلاه
            if day_name == "Saturday":
                return saturday_is_workday
            # باقي الأيام دوام
            return True

        emp_df["is_workday"] = emp_df["weekday"].apply(is_workday)
        emp_df["first_td"] = emp_df["first_punch_time"].apply(time_to_td)

        # =========================
        # ✅ التأخير: استثناء السبت للجميع (0 دائمًا يوم السبت)
        # =========================
        def calc_late(row):
            if row["weekday"] == "Saturday":
                return 0
            if not row["is_workday"]:
                return 0
            if row["first_td"] is None:
                return 0
            if row["first_td"] <= late_limit:
                return 0
            return int((row["first_td"] - late_limit).total_seconds() // 60)

        emp_df["late_minutes"] = emp_df.apply(calc_late, axis=1)

        # الغياب = أيام عمل متوقعة - أيام لديها أي سجل
        date_min = emp_df["date"].min()
        date_max = emp_df["date"].max()
        if pd.isna(date_min) or pd.isna(date_max):
            continue

        date_range = pd.date_range(date_min.normalize(), date_max.normalize(), freq="D")
        expected_days = [d for d in date_range if is_workday(d.day_name())]
        present_days = set(emp_df["date"].dt.date.dropna().unique())
        absent_days = [d for d in expected_days if d.date() not in present_days]

        # تفاصيل الغياب
        for d in absent_days:
            absence_details.append(
                {
                    "employee_id": emp_id,
                    "employee_no": emp_no,
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "job_title": emp_job,
                    "nationality": emp_nat,
                    "department": emp_dept,
                    "date": d.date(),
                    "weekday": d.day_name(),
                    "weekday_ar": weekday_ar(d.day_name()),
                    "schedule": schedule,
                }
            )

        # تفاصيل التأخير
        late_rows = emp_df[emp_df["late_minutes"] > 0].copy()
        if "date" in late_rows.columns:
            late_rows = late_rows.sort_values("date")

        for _, r in late_rows.iterrows():
            late_details.append(
                {
                    "employee_id": emp_id,
                    "employee_no": emp_no,
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "job_title": emp_job,
                    "nationality": emp_nat,
                    "department": emp_dept,
                    "date": r["date"].date() if pd.notna(r["date"]) else None,
                    "weekday": r["weekday"],
                    "weekday_ar": weekday_ar(r["weekday"]),
                    "late_minutes": int(r["late_minutes"]),
                    "schedule": schedule,
                    "first_punch": r.get("first_punch"),
                    "first_punch_time": r.get("first_punch_time"),
                }
            )

        results.append(
            {
                "employee_id": emp_id,
                "employee_no": emp_no,
                "name_ar": name_ar,
                "name_en": name_en,
                "job_title": emp_job,
                "is_saudi": is_saudi,
                "nationality_raw": emp_nat,
                "department": emp_dept,
                "schedule": schedule,
                "period_from": date_min.date(),
                "period_to": date_max.date(),
                "absent_days": len(absent_days),
                "late_days": int((emp_df["late_minutes"] > 0).sum()),
                "total_late_minutes": int(emp_df["late_minutes"].sum()),
            }
        )

    return pd.DataFrame(results), pd.DataFrame(late_details), pd.DataFrame(absence_details)
