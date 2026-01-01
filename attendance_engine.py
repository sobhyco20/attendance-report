# attendance_engine.py
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
    targets = {"employee id", "date"}
    for i in range(min(max_scan_rows, len(raw))):
        row = raw.iloc[i].astype(str).str.strip().str.lower().tolist()
        if targets.issubset(set(row)):
            return i
    return 0


def _read_attendance_any_format(file) -> pd.DataFrame:
    raw = pd.read_excel(file, header=None)
    hdr = _find_header_row(raw)
    columns = raw.iloc[hdr].tolist()
    df = raw.iloc[hdr + 1 :].copy()
    df.columns = columns
    df = df.dropna(how="all")
    return df


def _is_saudi(nat) -> bool:
    if nat is None or (isinstance(nat, float) and pd.isna(nat)):
        return True
    s = str(nat).strip().lower()
    if not s:
        return True
    s = re.sub(r"\s+", " ", s)

    keys = [
        "سعود", "سعودي", "سعودية", "السعودية", "السعوديه",
        "المملكة العربية السعودية", "المملكه العربيه السعوديه",
        "saudi", "saudi arabia", "kingdom of saudi arabia",
        "ksa", "k.s.a", "k s a",
    ]
    return any(k in s for k in keys)


def _norm_emp_id(x) -> str:
    s = "" if x is None else str(x).strip()
    if not s:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    return s.strip()


def _safe_split_hhmm(hhmm: str, fallback="08:00"):
    s = str(hhmm or "").strip()
    if not s:
        s = fallback
    if ":" not in s:
        s = fallback
    parts = s.split(":")
    if len(parts) < 2:
        parts = fallback.split(":")
    try:
        hh = int(float(parts[0]))
        mm = int(float(parts[1]))
    except Exception:
        hh, mm = 8, 0
    return f"{hh:02d}:{mm:02d}"


def _time_to_td(t):
    if t is None:
        return None
    try:
        if pd.isna(t):
            return None
    except Exception:
        pass

    if isinstance(t, dt.time):
        return dt.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)

    if isinstance(t, (dt.datetime, pd.Timestamp)):
        return dt.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)

    try:
        s = str(t).strip()
        if not s or s.lower() in ("nan", "nat", "none"):
            return None
        parts = s.split(":")
        if len(parts) >= 2:
            hh = int(float(parts[0]))
            mm = int(float(parts[1]))
            ss = int(float(parts[2])) if len(parts) >= 3 else 0
            return dt.timedelta(hours=hh, minutes=mm, seconds=ss)
    except Exception:
        return None

    return None


def _as_bool(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "نعم", "صح", "on", "ok", "✔", "✅")


def _to_hhmm(v, default_hhmm: str) -> str:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default_hhmm
        if isinstance(v, dt.time):
            return f"{int(v.hour):02d}:{int(v.minute):02d}"
        s = str(v).strip()
        if not s:
            return default_hhmm
        if re.match(r"^\d{1,2}:\d{1,2}$", s):
            hh, mm = s.split(":")
            return f"{int(hh):02d}:{int(mm):02d}"
        return default_hhmm
    except Exception:
        return default_hhmm


def _to_minutes(v, default: int) -> int:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return int(default)

        if isinstance(v, dt.time):
            return int(v.hour) * 60 + int(v.minute)

        if isinstance(v, dt.timedelta):
            return int(v.total_seconds() // 60)

        if isinstance(v, (int, float)):
            return int(v)

        s = str(v).strip()
        if not s:
            return int(default)

        if re.match(r"^\d{1,2}:\d{2}$", s):
            hh, mm = s.split(":")
            return int(hh) * 60 + int(mm)

        return int(float(s))
    except Exception:
        return int(default)


# =========================
# Payroll Period Helper
# نظام الرواتب: من 8 الشهر إلى 7 الشهر التالي
# ويعتبر راتب الشهر التالي
# =========================
def payroll_period_from_date(any_date) -> dict:
    d = pd.to_datetime(any_date, errors="coerce")
    if pd.isna(d):
        return {
            "period_start": None,
            "period_end": None,
            "payroll_month": None,
            "payroll_year": None,
        }

    # لو اليوم >= 8 => البداية 8 نفس الشهر، النهاية 7 الشهر التالي، شهر الراتب = الشهر التالي
    if int(d.day) >= 8:
        start = d.replace(day=8).normalize()
        if int(d.month) == 12:
            end = pd.Timestamp(year=int(d.year) + 1, month=1, day=7)
            payroll_month = 1
            payroll_year = int(d.year) + 1
        else:
            end = pd.Timestamp(year=int(d.year), month=int(d.month) + 1, day=7)
            payroll_month = int(d.month) + 1
            payroll_year = int(d.year)
        return {
            "period_start": start,
            "period_end": end.normalize(),
            "payroll_month": payroll_month,
            "payroll_year": payroll_year,
        }

    # لو اليوم من 1 إلى 7 => الفترة تبدأ 8 الشهر السابق وتنتهي 7 هذا الشهر، شهر الراتب = هذا الشهر
    if int(d.month) == 1:
        start = pd.Timestamp(year=int(d.year) - 1, month=12, day=8)
        end = pd.Timestamp(year=int(d.year), month=1, day=7)
        payroll_month = 1
        payroll_year = int(d.year)
    else:
        start = pd.Timestamp(year=int(d.year), month=int(d.month) - 1, day=8)
        end = pd.Timestamp(year=int(d.year), month=int(d.month), day=7)
        payroll_month = int(d.month)
        payroll_year = int(d.year)

    return {
        "period_start": start.normalize(),
        "period_end": end.normalize(),
        "payroll_month": payroll_month,
        "payroll_year": payroll_year,
    }


def process_attendance(
    attendance_file,
    start_time="08:00",
    grace_minutes=15,
    schedule_mode="by_nationality",  # by_nationality | auto | fri | fri_sat
    employees_df: pd.DataFrame | None = None,
    exceptions_df: pd.DataFrame | None = None,  # اختياري
):
    df = _read_attendance_any_format(attendance_file)

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

    df["employee_id"] = df["employee_id"].astype(str).str.strip().apply(_norm_emp_id)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df[pd.notna(df["date"])].copy()

    df["weekday"] = df["date"].dt.day_name()
    df["weekday_ar"] = df["weekday"].map(WEEKDAY_AR).fillna(df["weekday"])

    fp = pd.to_datetime(df.get("first_punch"), errors="coerce")
    df["first_punch_time"] = fp.dt.time

    # ========= دمج employees =========
    emp_flags_map = {}
    if employees_df is not None and not employees_df.empty:
        emp = employees_df.copy()

        emp = emp.rename(
            columns={
                "Personnel Number": "employee_id",
                "Employee ID": "employee_id",
                "Emp ID": "employee_id",
                "ID": "employee_id",
                "رقم الموظف": "employee_id",
                "كود الموظف": "employee_id",

                "Arabic name": "name_ar",
                "Search name": "name_en",
                "emp_name": "name_ar",

                "Contrac Profession": "job_title",

                "nationality": "nationality",
                "Nationality": "nationality",
                "الجنسية": "nationality",

                "Section | Department": "department_emp",
                "Department": "department_emp",

                "Employee No": "employee_no",
                "الرقم الوظيفي": "employee_no",

                # اختياري: تحديد دوام الجمعة/السبت لكل موظف
                "fri_work": "fri_work",
                "friday_work": "fri_work",
                "work_friday": "fri_work",
                "دوام الجمعة": "fri_work",

                "sat_work": "sat_work",
                "saturday_work": "sat_work",
                "work_saturday": "sat_work",
                "دوام السبت": "sat_work",
            }
        )

        if "employee_no" not in emp.columns:
            emp["employee_no"] = emp["employee_id"]

        emp["employee_id"] = emp["employee_id"].astype(str).str.strip().apply(_norm_emp_id)

        for _, r in emp.iterrows():
            k = _norm_emp_id(r.get("employee_id"))
            if not k:
                continue
            emp_flags_map[k] = {
                "fri_work": _as_bool(r.get("fri_work")) if "fri_work" in emp.columns else None,
                "sat_work": _as_bool(r.get("sat_work")) if "sat_work" in emp.columns else None,
            }

        keep_cols = ["employee_id"]
        for c in ["name_ar", "name_en", "job_title", "nationality", "employee_no", "department_emp"]:
            if c in emp.columns:
                keep_cols.append(c)

        df = df.merge(emp[keep_cols], on="employee_id", how="left")

    # ========= exceptions map (اختياري) =========
    ex_map = {}
    if exceptions_df is not None and not exceptions_df.empty:
        ex = exceptions_df.copy()
        ex = ex.rename(
            columns={
                "employee_id": "employee_id",
                "Employee ID": "employee_id",
                "Personnel Number": "employee_id",
                "Emp ID": "employee_id",
                "ID": "employee_id",
                "رقم الموظف": "employee_id",
                "كود الموظف": "employee_id",
                "sat_work": "sat_work",
                "sat_start": "sat_start",
                "sat_grace": "sat_grace",
                "fri_work": "fri_work",
            }
        )
        if "employee_id" in ex.columns:
            ex["employee_id"] = ex["employee_id"].astype(str).str.strip().apply(_norm_emp_id)
            for _, r in ex.iterrows():
                k = _norm_emp_id(r.get("employee_id"))
                if k:
                    ex_map[k] = r.to_dict()

    # ========= وقت الدوام =========
    start_time = _safe_split_hhmm(start_time, fallback="08:00")
    hh, mm = start_time.split(":")
    start_td = dt.timedelta(hours=int(hh), minutes=int(mm))
    late_limit = start_td + dt.timedelta(minutes=int(grace_minutes))

    results, late_details, absence_details = [], [], []

    def pick_first(series, fallback=""):
        if series is None:
            return fallback
        s = series.dropna()
        return s.iloc[0] if len(s) else fallback

    # ✅ Anchor عام من الملف (آخر تاريخ بالملف) = أساس فترة الرواتب
    global_anchor = df["date"].max()
    if pd.isna(global_anchor):
        global_anchor = None

    global_period = payroll_period_from_date(global_anchor) if global_anchor is not None else {
        "period_start": None, "period_end": None, "payroll_month": None, "payroll_year": None
    }

    for emp_id, emp_df in df.groupby("employee_id", dropna=False):
        emp_df = emp_df.copy()
        emp_id_str = _norm_emp_id(emp_id)

        name_ar = pick_first(emp_df.get("name_ar"), pick_first(emp_df.get("name_att"), ""))
        name_en = pick_first(emp_df.get("name_en"), "")
        emp_dept = pick_first(emp_df.get("department_emp"), pick_first(emp_df.get("department_att"), ""))
        emp_job = pick_first(emp_df.get("job_title"), "")
        emp_nat = pick_first(emp_df.get("nationality"), "")
        emp_no = pick_first(emp_df.get("employee_no"), emp_id_str)

        # ===== الافتراضي حسب الجنسية =====
        is_sa = _is_saudi(emp_nat)

        # non-saudi: الجمعة إجازة فقط => السبت دوام
        # saudi: الجمعة+السبت إجازة
        if schedule_mode == "by_nationality":
            base_fri_work = False
            base_sat_work = (not is_sa)
        elif schedule_mode == "fri":      # إجازة الجمعة فقط => السبت عمل
            base_fri_work = False
            base_sat_work = True
        elif schedule_mode == "fri_sat":  # إجازة الجمعة والسبت
            base_fri_work = False
            base_sat_work = False
        else:
            # auto: لو ظهر السبت في السجلات نفترض أنه يوم عمل
            base_fri_work = False
            base_sat_work = bool((emp_df["weekday"] == "Saturday").any())

        # ===== Overrides من employees.xlsx =====
        emp_flags = emp_flags_map.get(emp_id_str, {})
        emp_fri_override = emp_flags.get("fri_work", None)
        emp_sat_override = emp_flags.get("sat_work", None)

        # ===== Overrides من exceptions_df =====
        ex = ex_map.get(emp_id_str, {})
        ex_fri_override = _as_bool(ex.get("fri_work")) if "fri_work" in ex else None
        ex_sat_override = _as_bool(ex.get("sat_work")) if "sat_work" in ex else None

        fri_work = base_fri_work
        sat_work = base_sat_work

        if emp_fri_override is True or emp_fri_override is False:
            fri_work = bool(emp_fri_override)
        if emp_sat_override is True or emp_sat_override is False:
            sat_work = bool(emp_sat_override)

        if ex_fri_override is True or ex_fri_override is False:
            fri_work = bool(ex_fri_override)
        if ex_sat_override is True or ex_sat_override is False:
            sat_work = bool(ex_sat_override)

        # ===== إعدادات السبت (إن كان دوام) =====
        sat_start_time = _to_hhmm(ex.get("sat_start"), start_time)
        sat_start_time = _safe_split_hhmm(sat_start_time, fallback=start_time)
        sat_grace = _to_minutes(ex.get("sat_grace"), grace_minutes)

        hh2, mm2 = sat_start_time.split(":")
        sat_start_td = dt.timedelta(hours=int(hh2), minutes=int(mm2))
        sat_late_limit = sat_start_td + dt.timedelta(minutes=int(sat_grace))

        # ===== Workday logic =====
        def is_workday(day_name: str) -> bool:
            if day_name == "Friday":
                return bool(fri_work)
            if day_name == "Saturday":
                return bool(sat_work)
            return True

        emp_df["is_workday"] = emp_df["weekday"].apply(is_workday)
        emp_df["first_td"] = emp_df["first_punch_time"].apply(_time_to_td)

        def calc_late(row):
            if not bool(row.get("is_workday", False)):
                return 0

            first_td = row.get("first_td", None)
            if first_td is None:
                return 0
            try:
                if pd.isna(first_td):
                    return 0
            except Exception:
                pass

            limit = sat_late_limit if row.get("weekday") == "Saturday" else late_limit
            try:
                diff = first_td - limit
                mins = diff.total_seconds() // 60
                return 0 if mins <= 0 else int(mins)
            except Exception:
                return 0

        emp_df["late_minutes"] = emp_df.apply(calc_late, axis=1)

        # ✅ فترة الرواتب ثابتة من الملف (آخر تاريخ في الملف)
        p_start = global_period["period_start"]
        p_end = global_period["period_end"]
        payroll_month = global_period["payroll_month"]
        payroll_year = global_period["payroll_year"]

        if p_start is None or p_end is None:
            # fallback: لو لأي سبب فشل، خذ حدود شهر آخر تاريخ للموظف
            _max = emp_df["date"].max()
            if pd.isna(_max):
                continue
            d = pd.to_datetime(_max)
            p_start = d.replace(day=1).normalize()
            p_end = (p_start + pd.offsets.MonthEnd(0)).normalize()
            payroll_month = int(p_end.month)
            payroll_year = int(p_end.year)

        date_min = pd.to_datetime(p_start).normalize()
        date_max = pd.to_datetime(p_end).normalize()

        # نبني أيام متوقعة = أيام عمل فقط داخل فترة الرواتب
        date_range = pd.date_range(date_min, date_max, freq="D")
        expected_days = [d for d in date_range if is_workday(d.day_name())]

        present_days = set(emp_df["date"].dt.date.dropna().unique())
        absent_days = [d for d in expected_days if d.date() not in present_days]

        # ===== Label واضح =====
        def schedule_label():
            fri = "دوام" if fri_work else "إجازة"
            sat = "دوام" if sat_work else "إجازة"
            return f"الجمعة: {fri} | السبت: {sat}"

        label = schedule_label()

        for d in absent_days:
            absence_details.append(
                {
                    "employee_id": emp_id_str,
                    "employee_no": emp_no,
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "job_title": emp_job,
                    "nationality": emp_nat,
                    "department": emp_dept,
                    "date": d.date(),
                    "weekday": d.day_name(),
                    "weekday_ar": weekday_ar(d.day_name()),
                    "schedule": label,
                    "fri_work": bool(fri_work),
                    "sat_work": bool(sat_work),
                    "payroll_month": payroll_month,
                    "payroll_year": payroll_year,
                }
            )

        late_rows = emp_df[emp_df["late_minutes"] > 0].copy()
        if "date" in late_rows.columns:
            late_rows = late_rows.sort_values("date")

        for _, r in late_rows.iterrows():
            late_details.append(
                {
                    "employee_id": emp_id_str,
                    "employee_no": emp_no,
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "job_title": emp_job,
                    "nationality": emp_nat,
                    "department": emp_dept,
                    "date": r["date"].date() if pd.notna(r["date"]) else None,
                    "weekday": r["weekday"],
                    "weekday_ar": weekday_ar(r["weekday"]),
                    "late_minutes": int(r["late_minutes"] or 0),
                    "schedule": label,
                    "fri_work": bool(fri_work),
                    "sat_work": bool(sat_work),
                    "first_punch": r.get("first_punch"),
                    "first_punch_time": r.get("first_punch_time"),
                    "payroll_month": payroll_month,
                    "payroll_year": payroll_year,
                }
            )

        results.append(
            {
                "employee_id": emp_id_str,
                "employee_no": emp_no,
                "name_ar": name_ar,
                "name_en": name_en,
                "job_title": emp_job,
                "is_saudi": is_sa,
                "nationality_raw": emp_nat,
                "department": emp_dept,
                "schedule": label,
                "fri_work": bool(fri_work),
                "sat_work": bool(sat_work),
                "sat_start": sat_start_time if sat_work else "",
                "sat_grace": int(sat_grace) if sat_work else "",
                "period_from": pd.to_datetime(date_min).date(),
                "period_to": pd.to_datetime(date_max).date(),
                "payroll_month": int(payroll_month) if payroll_month else "",
                "payroll_year": int(payroll_year) if payroll_year else "",
                "absent_days": len(absent_days),
                "late_days": int((emp_df["late_minutes"] > 0).sum()),
                "total_late_minutes": int(emp_df["late_minutes"].sum()),
            }
        )

    return pd.DataFrame(results), pd.DataFrame(late_details), pd.DataFrame(absence_details)
