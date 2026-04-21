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


# =========================
# 🔥 أهم دالة (إصلاح الوقت)
# =========================
def time_to_td(t):
    if t is None or pd.isna(t):
        return None

    try:
        tt = pd.to_datetime(t, errors="coerce")
        if pd.isna(tt):
            return None

        # 🔥 الإصلاح هنا
        return dt.timedelta(
            hours=tt.hour,
            minutes=tt.minute,
            seconds=tt.second
        )
    except Exception:
        return None

# =========================
# المعالجة الرئيسية
# =========================


def process_attendance(
    attendance_file,
    start_time="08:00",
    grace_minutes=15,
    employees_df=None,
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

    # 🔥 تحويل الوقت إلى datetime
    df["first_punch_dt"] = pd.to_datetime(df["first_punch"], errors="coerce")
    df["last_punch_dt"] = pd.to_datetime(df["last_punch"], errors="coerce")

    # 🔥 تحويل إلى دقائق (أهم خطوة)
    df["first_td"] = (
        df["first_punch_dt"].dt.hour.fillna(0) * 60 +
        df["first_punch_dt"].dt.minute.fillna(0)
    )

    df["last_td"] = (
        df["last_punch_dt"].dt.hour.fillna(0) * 60 +
        df["last_punch_dt"].dt.minute.fillna(0)
    )

    # 🔥 وقت بداية الدوام بالدقائق
    hh, mm = start_time.split(":")
    start_minutes = int(hh) * 60 + int(mm)

    # 🔥 حد التأخير
    late_limit_minutes = start_minutes + grace_minutes

    # 🔥 نهاية الدوام
    end_minutes = 17 * 60

    results = []
    late_details = []

    for emp_id, emp_df in df.groupby("employee_id"):
        emp_df = emp_df.copy()

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
        emp_df["early_minutes"] = emp_df.apply(calc_early, axis=1)

        # التفاصيل
        for _, r in emp_df.iterrows():
            if r["late_minutes"] > 0 or r["early_minutes"] > 0:
                late_details.append({
                    "employee_id": emp_id,
                    "date": r["date"],
                    "late_minutes": int(r["late_minutes"]),
                    "early_minutes": int(r["early_minutes"]),
                })

        # الملخص
        results.append({
            "employee_id": emp_id,
            "late_days": int((emp_df["late_minutes"] > 0).sum()),
            "total_late_minutes": int(emp_df["late_minutes"].sum()),
            "early_days": int((emp_df["early_minutes"] > 0).sum()),
            "total_early_minutes": int(emp_df["early_minutes"].sum()),
        })

    return (
        pd.DataFrame(results),
        pd.DataFrame(late_details),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )

