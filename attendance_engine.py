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
    return WEEKDAY_AR.get(str(day).strip(), str(day))


# =========================
# قراءة ملف البصمة
# =========================
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
    df = raw.iloc[hdr + 1 :].copy()
    df.columns = raw.iloc[hdr].tolist()
    return df.dropna(how="all")


def _is_eid_holiday(d):
    return False


def shift_params_for_date(d):
    start = dt.timedelta(hours=8)
    late_limit = start + dt.timedelta(minutes=15)
    end = dt.timedelta(hours=17)
    return start, late_limit, end


# =========================
# المعالجة الرئيسية
# =========================
def process_attendance(
    attendance_file,
    start_time="08:00",
    grace_minutes=15,
    schedule_mode="by_nationality",
    employees_df=None,
    daily_required_hours=9.0,
    approved_leaves_df=None,
):
    df = _read_attendance_any_format(attendance_file)

    df = df.rename(columns={
        "Employee ID": "employee_id",
        "Date": "date",
        "First Punch": "first_punch",
        "Last Punch": "last_punch",
    })

    if "employee_id" not in df.columns or "date" not in df.columns:
        raise KeyError("ملف البصمة غير صحيح")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weekday"] = df["date"].dt.day_name()
    df["weekday_ar"] = df["weekday"].apply(weekday_ar)

    df["first_punch_dt"] = pd.to_datetime(df["first_punch"], errors="coerce")
    df["last_punch_dt"] = pd.to_datetime(df["last_punch"], errors="coerce")

    df["is_workday"] = df["weekday"] != "Friday"

    hh, mm = start_time.split(":")
    start_minutes = int(hh) * 60 + int(mm)
    late_limit_minutes = start_minutes + grace_minutes
    end_minutes = 17 * 60

    results = []
    late_details = []
    absence_details = []
    exempt_details = []
    leave_details = []

    for emp_id, emp_df in df.groupby("employee_id"):
        emp_df = emp_df.copy()

        emp_df["first_td"] = (
            emp_df["first_punch_dt"].dt.hour.fillna(0).astype(int) * 60 +
            emp_df["first_punch_dt"].dt.minute.fillna(0).astype(int)
        )

        emp_df["last_td"] = (
            emp_df["last_punch_dt"].dt.hour.fillna(0).astype(int) * 60 +
            emp_df["last_punch_dt"].dt.minute.fillna(0).astype(int)
        )

        def calc_late(row):
            first = row.get("first_td")
            if pd.isna(first):
                return 0
            if first <= late_limit_minutes:
                return 0
            return int(first - late_limit_minutes)

        def calc_early(row):
            last = row.get("last_td")
            if pd.isna(last):
                return 0
            if last >= end_minutes:
                return 0
            return int(end_minutes - last)

        emp_df["late_minutes"] = emp_df.apply(calc_late, axis=1)
        emp_df["early_leave_minutes"] = emp_df.apply(calc_early, axis=1)

        for _, r in emp_df.iterrows():
            if r["late_minutes"] > 0 or r["early_leave_minutes"] > 0:
                late_details.append({
                    "employee_id": emp_id,
                    "date": r["date"],
                    "late_minutes": int(r["late_minutes"]),
                    "early_leave_minutes": int(r["early_leave_minutes"]),
                })

        absent_days = emp_df[
            emp_df["first_punch_dt"].isna() &
            emp_df["last_punch_dt"].isna() &
            emp_df["is_workday"]
        ]

        for _, r in absent_days.iterrows():
            absence_details.append({
                "employee_id": emp_id,
                "date": r["date"],
                "weekday": r["weekday"],
                "weekday_ar": r["weekday_ar"],
            })

        results.append({
            "employee_id": emp_id,
            "period_from": emp_df["date"].min(),
            "period_to": emp_df["date"].max(),
            "absent_days": len(absent_days),
            "late_days": int((emp_df["late_minutes"] > 0).sum()),
            "total_late_minutes": int(emp_df["late_minutes"].sum()),
            "early_leave_days": int((emp_df["early_leave_minutes"] > 0).sum()),
            "total_early_leave_minutes": int(emp_df["early_leave_minutes"].sum()),
        })

    return (
        pd.DataFrame(results),
        pd.DataFrame(late_details),
        pd.DataFrame(absence_details),
        pd.DataFrame(exempt_details),
        pd.DataFrame(leave_details),
    )
