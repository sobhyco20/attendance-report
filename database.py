# =========================
# database.py
# =========================

import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "attendance.db"


# =========================
# الاتصال
# =========================

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# إنشاء الجداول
# =========================

def init_db():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS leaves (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        leave_id TEXT,
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
        attachment_data BLOB,

        notes TEXT,

        created_at TEXT,
        created_by TEXT
    )
    """)

  
    conn.commit()

    migrate_db()

    conn.close()


# =========================
# تحميل الإجازات
# =========================

def load_leaves_db():

    init_db()

    conn = get_connection()

    df = pd.read_sql_query(
        "SELECT * FROM leaves",
        conn
    )

    conn.close()

    return df


# =========================
# إضافة إجازة
# =========================

def insert_leave(record):

    init_db()

    conn = get_connection()
    cur = conn.cursor()

    attachment_name = ""
    attachment_data = None

    uploaded_file = record.get("uploaded_file")

    if uploaded_file is not None:

        attachment_name = uploaded_file.name
        attachment_data = uploaded_file.getvalue()

    cur.execute("""
    INSERT INTO leaves (

        leave_id,
        employee_id,
        employee_no,

        name_ar,
        name_en,

        department,
        job_title,

        leave_type,

        start_date,
        end_date,

        status,

        attachment_name,
        attachment_data,

        notes,

        created_at,
        created_by

    )

    VALUES (

        ?, ?, ?,
        ?, ?,
        ?, ?,
        ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?

    )
    """, (

        record.get("leave_id"),
        record.get("employee_id"),
        record.get("employee_no"),

        record.get("name_ar"),
        record.get("name_en"),

        record.get("department"),
        record.get("job_title"),

        record.get("leave_type"),

        str(record.get("start_date")),
        str(record.get("end_date")),

        record.get("status"),

        attachment_name,
        attachment_data,

        record.get("notes"),

        str(datetime.now()),
        record.get("created_by")

    ))

    conn.commit()
    conn.close()


# =========================
# حذف إجازة
# =========================

def delete_leave(leave_id):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        "DELETE FROM leaves WHERE leave_id=?",
        (leave_id,)
    )

    conn.commit()
    conn.close()


# =========================
# تحميل مرفق
# =========================

def get_attachment(leave_id):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""

        SELECT attachment_name,
               attachment_data

        FROM leaves

        WHERE leave_id=?

    """, (leave_id,))

    row = cur.fetchone()

    conn.close()

    if row:
        return {
            "name": row["attachment_name"],
            "data": row["attachment_data"]
        }

    return None


# =========================
# تحديث قاعدة البيانات
# =========================

def migrate_db():

    conn = get_connection()

    cur = conn.cursor()

    # إضافة attachment_data إذا غير موجود
    try:

        cur.execute("""

            ALTER TABLE leaves

            ADD COLUMN attachment_data BLOB

        """)

    except Exception:
        pass

    conn.commit()
    conn.close()
