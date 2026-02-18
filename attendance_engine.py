# =========================
# attendance_engine.py
# =========================
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


def _norm_str(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).strip()


def _detect_attendance_rule(emp_row: pd.Series) -> str:
    """
    يحاول تحديد قاعدة احتساب الحضور للموظف.
    المطلوب: المستثنين = daily_hours
    """
    candidates = [
        "attendance_calculation",
        "Attendance Calculation",
        "attendance rule",
        "Attendance Rule",
        "rule",
        "Rule",
        "مستثنى",
        "استثناء",
        "نوع الاحتساب",
        "طريقة الاحتساب",
    ]
    for c in candidates:
        if c in emp_row.index:
            v = _norm_str(emp_row.get(c))
            if v:
                v_l = v.strip().lower()
                if v_l in ["daily_hours", "daily hours", "hours", "exempt", "استثناء", "مستثنى"]:
                    return "daily_hours"
                if "daily" in v_l and "hour" in v_l:
                    return "daily_hours"
    return ""


# ✅ رمضان: من 18-02-2026 إلى 17-03-2026
RAMADAN_FROM = pd.Timestamp("2026-02-18")
RAMADAN_TO   = pd.Timestamp("2026-03-17")

# ✅ دوام رمضان
RAMADAN_START_TIME = "09:30"
RAMADAN_END_TIME   = "15:30"


def process_attendance(
    attendance_file,
    start_time="08:00",
    grace_minutes=15,
    schedule_mode="by_nationality",
    employees_df: pd.DataFrame | None = None,
    daily_required_hours: float = 9.0,   # ✅ موجودة بدون كسر البنية (لم تعد مستخدمة للمستثنين حسب طلبك)
):
    # 1) قراءة البصمة
    df = _read_attendance_any_format(attendance_file)

    # 2) rename
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
    lp = pd.to_datetime(df.get("last_punch"), errors="coerce")

    df["first_punch_dt"] = fp
    df["last_punch_dt"] = lp
    df["first_punch_time"] = fp.dt.time
    df["last_punch_time"] = lp.dt.time

    # 3) دمج بيانات الموظفين
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

        # ✅ احتساب المستثنى (قاعدة daily_hours) لو موجودة بأي عمود معروف
        if "attendance_calculation" not in emp.columns:
            for c in ["Attendance Calculation", "Attendance Rule", "rule", "Rule", "نوع الاحتساب", "طريقة الاحتساب", "مستثنى"]:
                if c in emp.columns:
                    emp["attendance_calculation"] = emp[c]
                    break

        if "employee_no" not in emp.columns:
            emp["employee_no"] = emp["employee_id"]

        df["employee_id"] = df["employee_id"].astype(str).str.strip()
        emp["employee_id"] = emp["employee_id"].astype(str).str.strip()

        keep_cols = ["employee_id"]
        for c in ["name_ar", "name_en", "job_title", "nationality", "employee_no", "department_emp", "attendance_calculation"]:
            if c in emp.columns:
                keep_cols.append(c)

        df = df.merge(emp[keep_cols], on="employee_id", how="left")

    # 4) إعدادات الوقت (افتراضي من المدخلات)
    hh, mm = start_time.split(":")
    default_start_td = dt.timedelta(hours=int(hh), minutes=int(mm))
    default_late_limit = default_start_td + dt.timedelta(minutes=int(grace_minutes))

    # ✅ إعدادات وقت رمضان
    rh, rm = RAMADAN_START_TIME.split(":")
    ram_start_td = dt.timedelta(hours=int(rh), minutes=int(rm))
    ram_late_limit = ram_start_td + dt.timedelta(minutes=int(grace_minutes))

    eh, em = RAMADAN_END_TIME.split(":")
    ram_overtime_threshold = dt.timedelta(hours=int(eh), minutes=int(em))

    # ✅ قاعدة الإضافي للمستثنى خارج رمضان: بعد 5 مساءً
    default_overtime_threshold = dt.timedelta(hours=17, minutes=0)

    def _is_ramadan_date(d) -> bool:
        if pd.isna(d) or d is None:
            return False
        dd = pd.to_datetime(d).normalize()
        return (dd >= RAMADAN_FROM) and (dd <= RAMADAN_TO)

    def shift_params_for_date(d):
        """
        يرجع (late_limit, overtime_threshold) حسب التاريخ
        late_limit: وقت بداية الدوام + السماح
        overtime_threshold: وقت نهاية الدوام (للمستثنى)
        """
        if _is_ramadan_date(d):
            return ram_late_limit, ram_overtime_threshold
        return default_late_limit, default_overtime_threshold

    results, late_details, absence_details, exempt_details = [], [], [], []

    def pick_first(series, fallback=""):
        if series is None:
            return fallback
        s = series.dropna()
        return s.iloc[0] if len(s) else fallback

    def time_to_td(t):
        # ✅ يمسك None و NaN و NaT
        if t is None or pd.isna(t):
            return None
        try:
            return dt.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except Exception:
            # ✅ لو جاء وقت كنص/قيمة غريبة
            tt = pd.to_datetime(t, errors="coerce")
            if pd.isna(tt):
                return None
            return dt.timedelta(hours=tt.hour, minutes=tt.minute, seconds=tt.second)


    for emp_id, emp_df in df.groupby("employee_id", dropna=False):
        emp_df = emp_df.copy()

        name_ar = pick_first(emp_df.get("name_ar"), pick_first(emp_df.get("name_att"), ""))
        name_en = pick_first(emp_df.get("name_en"), "")
        emp_dept = pick_first(emp_df.get("department_emp"), pick_first(emp_df.get("department_att"), ""))
        emp_job  = pick_first(emp_df.get("job_title"), "")
        emp_nat  = pick_first(emp_df.get("nationality"), "")
        emp_no   = pick_first(emp_df.get("employee_no"), emp_id)

        is_saudi = _is_saudi(emp_nat)

        # ✅ attendance rule
        attendance_rule = pick_first(emp_df.get("attendance_calculation"), "")
        attendance_rule = _norm_str(attendance_rule).lower()
        if attendance_rule in ["daily hours", "daily_hours", "hours", "exempt", "مستثنى", "استثناء"]:
            attendance_rule = "daily_hours"
        else:
            attendance_rule = ""

        # =========================
        # ✅ قاعدة السبت
        # =========================
        has_sat_presence = (emp_df["weekday"] == "Saturday").any()
        saturday_is_workday = (not is_saudi) and has_sat_presence
        schedule = "جمعة فقط" if saturday_is_workday else "جمعة وسبت"

        def is_workday(day_name: str) -> bool:
            if day_name == "Friday":
                return False
            if day_name == "Saturday":
                return saturday_is_workday
            return True

        emp_df["is_workday"] = emp_df["weekday"].apply(is_workday)

        # =========================
        # ✅ فترة الشهر: من 8 إلى 7
        # =========================
        any_date = emp_df["date"].dropna().iloc[0]
        start_date = any_date.replace(day=8)
        if any_date.day < 8:
            start_date = (start_date - pd.DateOffset(months=1))
        end_date = start_date + pd.DateOffset(months=1) - pd.DateOffset(days=1)

        date_min = start_date
        date_max = end_date
        if pd.isna(date_min) or pd.isna(date_max):
            continue

        # =========================
        # ✅ الغياب (مشترك للجميع)
        # =========================
        date_range = pd.date_range(date_min.normalize(), date_max.normalize(), freq="D")
        expected_days = [d for d in date_range if is_workday(d.day_name())]
        present_days = set(emp_df["date"].dt.date.dropna().unique())
        absent_days = [d for d in expected_days if d.date() not in present_days]

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
                    "attendance_calculation": attendance_rule,
                }
            )

        # =========================
        # ✅ التأخير/الإضافي
        # =========================
        emp_df["first_td"] = emp_df["first_punch_time"].apply(time_to_td)
        emp_df["last_td"] = emp_df["last_punch_time"].apply(time_to_td)

        # ---- حالة الموظف العادي
        if attendance_rule != "daily_hours":

            def calc_late(row):
                if row["weekday"] == "Saturday":
                    return 0
                if not row["is_workday"]:
                    return 0
                if row["first_td"] is None:
                    return 0

                late_limit_day, _ = shift_params_for_date(row.get("date"))
                if row["first_td"] <= late_limit_day:
                    return 0
                return int((row["first_td"] - late_limit_day).total_seconds() // 60)

            emp_df["late_minutes"] = emp_df.apply(calc_late, axis=1)

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
                        "last_punch": r.get("last_punch"),
                        "last_punch_time": r.get("last_punch_time"),
                        "attendance_calculation": attendance_rule,
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
                    "attendance_calculation": "",
                    "total_overtime_minutes": 0,
                }
            )

        # ---- حالة المستثنى: daily_hours
        else:
            # نجمع باليوم (قد توجد سجلات مكررة)
            # نأخذ أول دخول = min first_punch_dt ، آخر خروج = max last_punch_dt
            day_group = emp_df.dropna(subset=["date"]).copy()
            day_group["date_only"] = day_group["date"].dt.date

            agg = (
                day_group.groupby("date_only", as_index=False)
                .agg(
                    weekday=("weekday", "first"),
                    weekday_ar=("weekday_ar", "first"),
                    is_workday=("is_workday", "first"),
                    first_in_dt=("first_punch_dt", "min"),
                    last_out_dt=("last_punch_dt", "max"),
                )
            )

            # تحويل أول/آخر بصمة إلى time و td
            agg["first_punch_time"] = agg["first_in_dt"].dt.time
            agg["last_punch_time"] = agg["last_out_dt"].dt.time
            agg["first_td"] = agg["first_punch_time"].apply(time_to_td)
            agg["last_td"] = agg["last_punch_time"].apply(time_to_td)

            # ✅ worked_minutes (للعرض فقط)
            worked_minutes_list = []
            late_list = []
            overtime_list = []

            for _, row in agg.iterrows():
                if not bool(row["is_workday"]):
                    worked_minutes = 0
                    late_m = 0
                    overtime_m = 0
                else:
                    fi = row["first_in_dt"]
                    lo = row["last_out_dt"]

                    # worked
                    if pd.isna(fi) or pd.isna(lo):
                        worked_minutes = 0
                    else:
                        delta = lo - fi
                        worked_minutes = max(0, int(delta.total_seconds() // 60))

                    # ✅ معايير اليوم (رمضان/غيره)
                    late_limit_day, overtime_thr_day = shift_params_for_date(row.get("date_only"))

                    # ✅ late: بعد بداية الدوام + السماح
                    if row["first_td"] is None:
                        late_m = 0
                    elif row["first_td"] <= late_limit_day:
                        late_m = 0
                    else:
                        late_m = int((row["first_td"] - late_limit_day).total_seconds() // 60)

                    # ✅ overtime: كل الوقت بعد نهاية الدوام
                    if row["last_td"] is None:
                        overtime_m = 0
                    elif row["last_td"] <= overtime_thr_day:
                        overtime_m = 0
                    else:
                        overtime_m = int((row["last_td"] - overtime_thr_day).total_seconds() // 60)

                worked_minutes_list.append(worked_minutes)
                late_list.append(late_m)
                overtime_list.append(overtime_m)

            agg["worked_minutes"] = worked_minutes_list
            agg["late_minutes"] = late_list
            agg["overtime_minutes"] = overtime_list

            agg["date"] = pd.to_datetime(agg["date_only"])

            # ✅ نعرض فقط الأيام التي بها (تأخير صباحي أو تعويض بعد نهاية الدوام)
            interesting = agg[(agg["late_minutes"] > 0) | (agg["overtime_minutes"] > 0)].copy()
            interesting = interesting.sort_values("date")

            total_late = int(agg["late_minutes"].sum())
            total_overtime = int(agg["overtime_minutes"].sum())

            for _, r in interesting.iterrows():
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
                        "weekday_ar": r["weekday_ar"],
                        "late_minutes": int(r["late_minutes"]),
                        "overtime_minutes": int(r["overtime_minutes"]),
                        "worked_minutes": int(r["worked_minutes"]),
                        "schedule": schedule,
                        "first_punch_time": r.get("first_punch_time"),
                        "last_punch_time": r.get("last_punch_time"),
                        "attendance_calculation": "daily_hours",
                    }
                )

                exempt_details.append(
                    {
                        "employee_id": emp_id,
                        "employee_no": emp_no,
                        "name_ar": name_ar,
                        "department": emp_dept,
                        "date": r["date"].date(),
                        "weekday_ar": r["weekday_ar"],
                        "first_in": r.get("first_punch_time"),
                        "last_out": r.get("last_punch_time"),
                        "worked_minutes": int(r["worked_minutes"]),
                        "late_minutes": int(r["late_minutes"]),
                        "overtime_minutes": int(r["overtime_minutes"]),
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

                    "late_days": int((agg["late_minutes"] > 0).sum()),
                    "total_late_minutes": total_late,

                    "attendance_calculation": "daily_hours",

                    "total_overtime_minutes": total_overtime,
                }
            )

    return (
        pd.DataFrame(results),
        pd.DataFrame(late_details),
        pd.DataFrame(absence_details),
        pd.DataFrame(exempt_details),
    )
