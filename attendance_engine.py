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


RAMADAN_FROM = pd.Timestamp("2026-02-18")
RAMADAN_TO = pd.Timestamp("2026-03-18")
RAMADAN_START_TIME = "09:30"
RAMADAN_END_TIME = "15:30"
DEFAULT_END_TIME = "17:00"

EID_FROM = pd.Timestamp("2026-03-19")
EID_TO = pd.Timestamp("2026-03-23")


def _is_eid_holiday(d) -> bool:
    if pd.isna(d) or d is None:
        return False
    dd = pd.to_datetime(d).normalize()
    return (dd >= EID_FROM) and (dd <= EID_TO)


def _prepare_leaves_df(approved_leaves_df: pd.DataFrame | None) -> pd.DataFrame:
    if approved_leaves_df is None or approved_leaves_df.empty:
        return pd.DataFrame()

    lv = approved_leaves_df.copy()
    rename_map = {
        "employee_id": "employee_id",
        "Employee ID": "employee_id",
        "Personnel Number": "employee_id",
        "Emp ID": "employee_id",
        "employee_no": "employee_no",
        "Employee No": "employee_no",
        "name_ar": "name_ar",
        "Arabic name": "name_ar",
        "name_en": "name_en",
        "Search name": "name_en",
        "leave_type": "leave_type",
        "type": "leave_type",
        "نوع الإجازة": "leave_type",
        "start_date": "start_date",
        "from_date": "start_date",
        "من": "start_date",
        "end_date": "end_date",
        "to_date": "end_date",
        "إلى": "end_date",
        "status": "status",
        "approval_status": "status",
        "الحالة": "status",
        "attachment_name": "attachment_name",
        "attachment_path": "attachment_path",
        "notes": "notes",
    }
    lv = lv.rename(columns={k: v for k, v in rename_map.items() if k in lv.columns})

    if "employee_id" not in lv.columns and "employee_no" in lv.columns:
        lv["employee_id"] = lv["employee_no"]
    if "employee_no" not in lv.columns and "employee_id" in lv.columns:
        lv["employee_no"] = lv["employee_id"]

    if "employee_id" not in lv.columns or "start_date" not in lv.columns or "end_date" not in lv.columns:
        return pd.DataFrame()

    lv["employee_id"] = lv["employee_id"].astype(str).str.strip()
    lv["employee_no"] = lv.get("employee_no", lv["employee_id"]).astype(str).str.strip()
    lv["start_date"] = pd.to_datetime(lv["start_date"], errors="coerce").dt.normalize()
    lv["end_date"] = pd.to_datetime(lv["end_date"], errors="coerce").dt.normalize()
    lv = lv.dropna(subset=["employee_id", "start_date", "end_date"]).copy()

    if "status" not in lv.columns:
        lv["status"] = "معتمدة"

    lv["status"] = lv["status"].fillna("").astype(str).str.strip()
    approved_tokens = {"approved", "approve", "معتمد", "معتمدة", "اعتماد", "تمت الموافقة", "active", "نشط"}
    lv = lv[lv["status"].str.lower().isin({t.lower() for t in approved_tokens}) | (lv["status"] == "")].copy()

    if "leave_type" not in lv.columns:
        lv["leave_type"] = "إجازة"
    if "attachment_name" not in lv.columns:
        lv["attachment_name"] = ""
    if "attachment_path" not in lv.columns:
        lv["attachment_path"] = ""
    if "notes" not in lv.columns:
        lv["notes"] = ""

    return lv.sort_values(["employee_id", "start_date", "end_date"])



def process_attendance(
    attendance_file,
    start_time="08:00",
    grace_minutes=15,
    schedule_mode="by_nationality",
    employees_df: pd.DataFrame | None = None,
    daily_required_hours: float = 9.0,
    approved_leaves_df: pd.DataFrame | None = None,
):
    df = _read_attendance_any_format(attendance_file)
    leaves_df = _prepare_leaves_df(approved_leaves_df)

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

    hh, mm = start_time.split(":")
    default_start_td = dt.timedelta(hours=int(hh), minutes=int(mm))
    default_late_limit = default_start_td + dt.timedelta(minutes=int(grace_minutes))

    dh, dm = DEFAULT_END_TIME.split(":")
    default_end_td = dt.timedelta(hours=int(dh), minutes=int(dm))

    rh, rm = RAMADAN_START_TIME.split(":")
    ram_start_td = dt.timedelta(hours=int(rh), minutes=int(rm))
    ram_late_limit = ram_start_td + dt.timedelta(minutes=int(grace_minutes))

    eh, em = RAMADAN_END_TIME.split(":")
    ram_end_td = dt.timedelta(hours=int(eh), minutes=int(em))

    def _is_ramadan_date(d) -> bool:
        if pd.isna(d) or d is None:
            return False
        dd = pd.to_datetime(d).normalize()
        return (dd >= RAMADAN_FROM) and (dd <= RAMADAN_TO)

    def shift_params_for_date(d):
        if _is_ramadan_date(d):
            return ram_start_td, ram_late_limit, ram_end_td
        return default_start_td, default_late_limit, default_end_td

    results, late_details, absence_details, exempt_details, leave_details = [], [], [], [], []

    def pick_first(series, fallback=""):
        if series is None:
            return fallback
        s = series.dropna()
        return s.iloc[0] if len(s) else fallback

    def time_to_td(t):
        if t is None or pd.isna(t):
            return None
        try:
            return dt.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except Exception:
            tt = pd.to_datetime(t, errors="coerce")
            if pd.isna(tt):
                return None
            return dt.timedelta(hours=tt.hour, minutes=tt.minute, seconds=tt.second)

    for emp_id, emp_df in df.groupby("employee_id", dropna=False):
        emp_df = emp_df.copy()
        emp_id = str(emp_id).strip()

        name_ar = pick_first(emp_df.get("name_ar"), pick_first(emp_df.get("name_att"), ""))
        name_en = pick_first(emp_df.get("name_en"), "")
        emp_dept = pick_first(emp_df.get("department_emp"), pick_first(emp_df.get("department_att"), ""))
        emp_job = pick_first(emp_df.get("job_title"), "")
        emp_nat = pick_first(emp_df.get("nationality"), "")
        emp_no = pick_first(emp_df.get("employee_no"), emp_id)

        is_saudi = _is_saudi(emp_nat)

        attendance_rule = pick_first(emp_df.get("attendance_calculation"), "")
        attendance_rule = _norm_str(attendance_rule).lower()
        if attendance_rule in ["daily hours", "daily_hours", "hours", "exempt", "مستثنى", "استثناء"]:
            attendance_rule = "daily_hours"
        else:
            attendance_rule = ""

        has_sat_presence = (emp_df["weekday"] == "Saturday").any()
        saturday_is_workday = (not is_saudi) and has_sat_presence
        schedule = "جمعة فقط" if saturday_is_workday else "جمعة وسبت"

        def is_workday(day_name: str, date_val=None) -> bool:
            if _is_eid_holiday(date_val):
                return False
            if day_name == "Friday":
                return False
            if day_name == "Saturday":
                return saturday_is_workday
            return True

        emp_df["is_workday"] = emp_df.apply(lambda r: is_workday(r["weekday"], r["date"]), axis=1)

        any_date = emp_df["date"].dropna().iloc[0]
        start_date = any_date.replace(day=8)
        if any_date.day < 8:
            start_date = (start_date - pd.DateOffset(months=1))
        end_date = start_date + pd.DateOffset(months=1) - pd.DateOffset(days=1)

        date_min = start_date
        date_max = end_date
        if pd.isna(date_min) or pd.isna(date_max):
            continue

        date_range = pd.date_range(date_min.normalize(), date_max.normalize(), freq="D")
        expected_days = [d for d in date_range if is_workday(d.day_name(), d)]
        present_days = set(emp_df["date"].dt.date.dropna().unique())

        emp_leaves = pd.DataFrame()
        leave_dates = set()
        if not leaves_df.empty:
            emp_leaves = leaves_df[leaves_df["employee_id"] == emp_id].copy()
            if not emp_leaves.empty:
                emp_leaves = emp_leaves[(emp_leaves["end_date"] >= date_min.normalize()) & (emp_leaves["start_date"] <= date_max.normalize())].copy()
                for _, lv in emp_leaves.iterrows():
                    overlap_start = max(lv["start_date"], date_min.normalize())
                    overlap_end = min(lv["end_date"], date_max.normalize())
                    for d in pd.date_range(overlap_start, overlap_end, freq="D"):
                        if is_workday(d.day_name(), d):
                            leave_dates.add(d.date())
                            leave_details.append(
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
                                    "leave_type": lv.get("leave_type", "إجازة"),
                                    "status": lv.get("status", "معتمدة"),
                                    "attachment_name": lv.get("attachment_name", ""),
                                    "attachment_path": lv.get("attachment_path", ""),
                                    "notes": lv.get("notes", ""),
                                    "leave_start": lv.get("start_date"),
                                    "leave_end": lv.get("end_date"),
                                }
                            )

        absent_days = [d for d in expected_days if d.date() not in present_days and d.date() not in leave_dates]

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

        emp_df["first_td"] = emp_df["first_punch_time"].apply(time_to_td)
        emp_df["last_td"] = emp_df["last_punch_time"].apply(time_to_td)

        if attendance_rule != "daily_hours":
            def calc_late(row):
                first = row.get("first_td")
            
                if pd.isna(first):
                    return 0
            
                if first <= late_limit_minutes:
                    return 0
            
                return int(first - late_limit_minutes)

            def calc_early_leave(row):
                if row["weekday"] == "Saturday":
                    return 0
                if not row["is_workday"] or _is_eid_holiday(row.get("date")):
                    return 0
                if row["last_td"] is None:
                    return 0

                _, _, end_td_day = shift_params_for_date(row.get("date"))
                if row["last_td"] >= end_td_day:
                    return 0
                return int((end_td_day - row["last_td"]).total_seconds() // 60)

            emp_df["late_minutes"] = emp_df.apply(calc_late, axis=1)
            emp_df["early_leave_minutes"] = emp_df.apply(calc_early_leave, axis=1)

            detail_rows = emp_df[(emp_df["late_minutes"] > 0) | (emp_df["early_leave_minutes"] > 0)].copy()
            if "date" in detail_rows.columns:
                detail_rows = detail_rows.sort_values("date")

            for _, r in detail_rows.iterrows():
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
                        "early_leave_minutes": int(r["early_leave_minutes"]),
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
                    "approved_leave_days": len(leave_dates),
                    "late_days": int((emp_df["late_minutes"] > 0).sum()),
                    "total_late_minutes": int(emp_df["late_minutes"].sum()),
                    "early_leave_days": int((emp_df["early_leave_minutes"] > 0).sum()),
                    "total_early_leave_minutes": int(emp_df["early_leave_minutes"].sum()),
                    "attendance_calculation": "",
                    "total_overtime_minutes": 0,
                }
            )
        else:
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

            agg["first_punch_time"] = agg["first_in_dt"].dt.time
            agg["last_punch_time"] = agg["last_out_dt"].dt.time
            agg["first_td"] = agg["first_punch_time"].apply(time_to_td)
            agg["last_td"] = agg["last_punch_time"].apply(time_to_td)

            worked_minutes_list = []
            late_list = []
            overtime_list = []
            early_leave_list = []

            for _, row in agg.iterrows():
                if not bool(row["is_workday"]) or _is_eid_holiday(row.get("date_only")):
                    worked_minutes = 0
                    late_m = 0
                    overtime_m = 0
                    early_leave_m = 0
                else:
                    fi = row["first_in_dt"]
                    lo = row["last_out_dt"]

                    if pd.isna(fi) or pd.isna(lo):
                        worked_minutes = 0
                    else:
                        delta = lo - fi
                        worked_minutes = max(0, int(delta.total_seconds() // 60))

                    _, late_limit_day, end_td_day = shift_params_for_date(row.get("date_only"))

                    if row["first_td"] is None:
                        late_m = 0
                    elif row["first_td"] <= late_limit_day:
                        late_m = 0
                    else:
                        late_m = int((row["first_td"] - late_limit_day).total_seconds() // 60)

                    if row["last_td"] is None:
                        overtime_m = 0
                    elif row["last_td"] <= end_td_day:
                        overtime_m = 0
                    else:
                        overtime_m = int((row["last_td"] - end_td_day).total_seconds() // 60)

                    if row["last_td"] is None:
                        early_leave_m = 0
                    elif row["last_td"] >= end_td_day:
                        early_leave_m = 0
                    else:
                        early_leave_m = int((end_td_day - row["last_td"]).total_seconds() // 60)

                worked_minutes_list.append(worked_minutes)
                late_list.append(late_m)
                overtime_list.append(overtime_m)
                early_leave_list.append(early_leave_m)

            agg["worked_minutes"] = worked_minutes_list
            agg["late_minutes"] = late_list
            agg["overtime_minutes"] = overtime_list
            agg["early_leave_minutes"] = early_leave_list
            agg["date"] = pd.to_datetime(agg["date_only"])

            interesting = agg[
                (agg["late_minutes"] > 0) |
                (agg["overtime_minutes"] > 0) |
                (agg["early_leave_minutes"] > 0)
            ].copy().sort_values("date")

            total_late = int(agg["late_minutes"].sum())
            total_overtime = int(agg["overtime_minutes"].sum())
            total_early_leave = int(agg["early_leave_minutes"].sum())

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
                        "early_leave_minutes": int(r["early_leave_minutes"]),
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
                        "early_leave_minutes": int(r["early_leave_minutes"]),
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
                    "approved_leave_days": len(leave_dates),
                    "late_days": int((agg["late_minutes"] > 0).sum()),
                    "total_late_minutes": total_late,
                    "early_leave_days": int((agg["early_leave_minutes"] > 0).sum()),
                    "total_early_leave_minutes": total_early_leave,
                    "attendance_calculation": "daily_hours",
                    "total_overtime_minutes": total_overtime,
                }
            )

    return (
        pd.DataFrame(results),
        pd.DataFrame(late_details),
        pd.DataFrame(absence_details),
        pd.DataFrame(exempt_details),
        pd.DataFrame(leave_details),
    )
