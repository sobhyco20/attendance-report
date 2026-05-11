# =========================
# database.py
# =========================

import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "attendance.db"


# =========================================================
# CONNECTION
# =========================================================

def get_connection():

    conn = sqlite3.connect(

        DB_NAME,

        check_same_thread=False

    )

    conn.row_factory = sqlite3.Row

    return conn


# =========================================================
# INIT DATABASE
# =========================================================

def init_db():

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""

    CREATE TABLE IF NOT EXISTS leaves (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        leave_id TEXT UNIQUE,

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

    conn.close()

    migrate_db()


# =========================================================
# MIGRATION
# =========================================================

def migrate_db():

    conn = get_connection()

    cur = conn.cursor()

    columns = []

    try:

        cur.execute(

            "PRAGMA table_info(leaves)"

        )

        columns = [

            row[1]

            for row in cur.fetchall()

        ]

    except Exception:
        pass

    # =====================================================
    # attachment_data
    # =====================================================

    if "attachment_data" not in columns:

        try:

            cur.execute("""

                ALTER TABLE leaves

                ADD COLUMN attachment_data BLOB

            """)

        except Exception:
            pass

    # =====================================================
    # attachment_name
    # =====================================================

    if "attachment_name" not in columns:

        try:

            cur.execute("""

                ALTER TABLE leaves

                ADD COLUMN attachment_name TEXT

            """)

        except Exception:
            pass

    conn.commit()

    conn.close()


# =========================================================
# LOAD LEAVES
# =========================================================

def load_leaves_db():

    init_db()

    conn = get_connection()

    try:

        df = pd.read_sql_query(

            """

            SELECT *

            FROM leaves

            ORDER BY start_date DESC

            """,

            conn

        )

    except Exception:

        df = pd.DataFrame()

    conn.close()

    return df


# =========================================================
# CHECK DUPLICATE
# =========================================================

def leave_exists(

    employee_id,
    leave_type,
    start_date,
    end_date

):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""

        SELECT COUNT(*)

        FROM leaves

        WHERE

            employee_id = ?
            AND leave_type = ?
            AND start_date = ?
            AND end_date = ?

    """, (

        str(employee_id),
        str(leave_type),
        str(start_date),
        str(end_date)

    ))

    count = cur.fetchone()[0]

    conn.close()

    return count > 0


# =========================================================
# INSERT LEAVE
# =========================================================

def insert_leave(record):

    init_db()

    # =====================================================
    # منع التكرار
    # =====================================================

    exists = leave_exists(

        record.get("employee_id"),

        record.get("leave_type"),

        record.get("start_date"),

        record.get("end_date")

    )

    if exists:

        return False

    conn = get_connection()

    cur = conn.cursor()

    attachment_name = ""
    attachment_data = None

    uploaded_file = record.get(

        "uploaded_file"

    )

    if uploaded_file is not None:

        try:

            attachment_name = uploaded_file.name

            attachment_data = uploaded_file.getvalue()

        except Exception:

            attachment_name = ""

            attachment_data = None

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

        str(record.get("employee_id")),
        str(record.get("employee_no")),

        str(record.get("name_ar")),
        str(record.get("name_en")),

        str(record.get("department")),
        str(record.get("job_title")),

        str(record.get("leave_type")),

        str(record.get("start_date")),
        str(record.get("end_date")),

        str(record.get("status")),

        attachment_name,
        attachment_data,

        str(record.get("notes")),

        str(datetime.now()),
        str(record.get("created_by"))

    ))

    conn.commit()

    conn.close()

    return True


# =========================================================
# DELETE LEAVE
# =========================================================

def delete_leave(leave_id):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(

        """

        DELETE FROM leaves

        WHERE leave_id = ?

        """,

        (leave_id,)

    )

    conn.commit()

    conn.close()


# =========================================================
# GET ATTACHMENT
# =========================================================

def get_attachment(leave_id):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""

        SELECT

            attachment_name,
            attachment_data

        FROM leaves

        WHERE leave_id = ?

    """, (leave_id,))

    row = cur.fetchone()

    conn.close()

    if row:

        return {

            "name": row["attachment_name"],

            "data": row["attachment_data"]

        }

    return None


# =========================================================
# UPDATE LEAVE
# =========================================================

def update_leave(

    leave_id,
    data: dict

):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""

        UPDATE leaves

        SET

            leave_type = ?,
            start_date = ?,
            end_date = ?,
            notes = ?,
            status = ?

        WHERE leave_id = ?

    """, (

        str(data.get("leave_type")),

        str(data.get("start_date")),

        str(data.get("end_date")),

        str(data.get("notes")),

        str(data.get("status")),

        str(leave_id)

    ))

    conn.commit()

    conn.close()
