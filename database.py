import sqlite3
import pandas as pd

DB_PATH = "attendance.db"

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS leaves (

    leave_id TEXT PRIMARY KEY,

    employee_id TEXT,
    employee_no TEXT,

    name_ar TEXT,
    name_en TEXT,

    department TEXT,
    job_title TEXT,

    leave_type TEXT,

    start_date TEXT,
    end_date TEXT,

    status TEXT,

    attachment_name TEXT,
    attachment_path TEXT,

    notes TEXT,

    created_at TEXT,
    created_by TEXT
)
""")

conn.commit()


def load_leaves_db():

    try:
        df = pd.read_sql(
            "SELECT * FROM leaves",
            conn
        )

        return df

    except Exception:
        return pd.DataFrame()


def insert_leave(record):

    cursor.execute("""

    INSERT OR REPLACE INTO leaves VALUES (

        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?

    )

    """, (

        record["leave_id"],

        record["employee_id"],
        record["employee_no"],

        record["name_ar"],
        record["name_en"],

        record["department"],
        record["job_title"],

        record["leave_type"],

        str(record["start_date"]),
        str(record["end_date"]),

        record["status"],

        record["attachment_name"],
        record["attachment_path"],

        record["notes"],

        str(record["created_at"]),
        record["created_by"],
    ))

    conn.commit()


def delete_leave(leave_id):

    cursor.execute(
        "DELETE FROM leaves WHERE leave_id=?",
        (leave_id,)
    )

    conn.commit()