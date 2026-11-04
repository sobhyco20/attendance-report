# =========================
# app.py — نظام الحضور والإجازات (Streamlit)
#   الملفات:
#     core.py            ثوابت ودوال مساعدة
#     store.py           الحفظ والقراءة (Supabase أو ملفات محلية)
#     supabase_store.py  الاتصال بـ Supabase
#     pdf_reports.py     تقارير PDF
#     attendance_engine.py  احتساب البصمة
# =========================
import os
import zlib
import datetime as dt
import time
from io import BytesIO

import pandas as pd
import streamlit as st

from attendance_engine import process_attendance
from core import *  # noqa: F401,F403
import store
from pdf_reports import build_pdf, build_leaves_pdf, build_sick_leave_pdf, build_all_leave_summary_pdf

# streamlit_cookies_manager بيستخدم st.cache اللي اتشالت من النسخ الحديثة
if not hasattr(st, "cache"):
    st.cache = st.cache_data

from streamlit_cookies_manager import EncryptedCookieManager  # noqa: E402

st.set_page_config(page_title="نظام الحضور والإجازات", page_icon="📊", layout="wide")

# =========================================================
# التصميم — ألوان فاتحة
# =========================================================
st.markdown("""
<style>
:root{
  --bg:#f5f7fb; --card:#ffffff; --line:#e2e8f0; --text:#0f172a; --muted:#64748b;
  --primary:#2563eb; --primary-soft:#eff6ff; --ok:#16a34a; --bad:#dc2626; --warn:#d97706;
}
.stApp{ background:var(--bg); color:var(--text); }
.block-container{ padding-top:1.4rem; max-width:100% !important; }
header[data-testid="stHeader"]{ background:transparent; }

/* RTL للنصوص */
.stMarkdown, h1,h2,h3,h4,h5,h6, p, label, div[data-testid="stMarkdownContainer"]{ direction:rtl; text-align:right; }
div[data-testid="stHorizontalBlock"]{ direction:rtl; }
div[data-testid="stWidgetLabel"]{ direction:rtl; text-align:right; width:100%; }
div[data-testid="stWidgetLabel"] label p{ color:#334155 !important; font-weight:600 !important; }

/* الشريط الجانبي يمين */
div[data-testid="stAppViewContainer"]{ display:flex !important; }
section[data-testid="stSidebar"]{ order:2 !important; direction:rtl; background:#ffffff !important; border-left:1px solid var(--line); }
div[data-testid="stMain"], div.main{ order:1 !important; }
button[data-testid="stSidebarCollapseButton"] svg, button[data-testid="stBaseButton-headerNoPadding"] svg{ transform:scaleX(-1); }

/* العنوان العلوي */
.app-head{ display:flex; justify-content:space-between; align-items:center; background:linear-gradient(135deg,#2563eb,#1d4ed8);
  color:#fff; border-radius:16px; padding:16px 22px; margin-bottom:14px; direction:rtl; }
.app-head .t{ font-size:22px; font-weight:800; }
.app-head .s{ font-size:13px; opacity:.85; }

/* التنقل */
div[data-testid="stButtonGroup"]{ direction:rtl; justify-content:center; display:flex; }
div[data-testid="stButtonGroup"] button{ font-weight:700; }
.subnav-gap{ height:6px; }

/* الكروت */
.card{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; margin-bottom:12px;
  direction:rtl; text-align:right; box-shadow:0 1px 2px rgba(15,23,42,.04); }
.card-title{ font-size:16px; font-weight:800; color:var(--text); margin-bottom:6px; }
.hint{ background:var(--primary-soft); border-right:4px solid var(--primary); border-radius:10px; padding:10px 12px;
  color:#1e3a8a; font-size:13px; margin-bottom:10px; direction:rtl; }
.hero-card{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px; margin-bottom:14px; direction:rtl; text-align:right; }
.hero-title{ font-size:22px; font-weight:800; color:var(--text); }
.hero-sub{ font-size:13px; color:var(--muted); }
.grid-note{ background:var(--card); border:1px dashed #cbd5e1; border-radius:10px; padding:12px; font-size:13px; color:#334155; direction:rtl; text-align:right; }

/* المؤشرات */
.small-kpi{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; text-align:center; }
.small-kpi .n{ font-size:22px; font-weight:800; color:var(--primary); }
.small-kpi .t{ font-size:12px; color:var(--muted); }
div[data-testid="stMetric"]{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 12px; }

.net-box{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; direction:rtl; text-align:right; }
.net-title{ font-weight:800; }
.net-big{ font-size:26px; font-weight:800; }
.net-sub{ font-size:12px; color:var(--muted); margin-top:4px; }
.net-row{ display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }
.net-pill{ background:var(--bg); border:1px solid var(--line); border-radius:999px; padding:6px 14px; font-size:13px; }
.net-good{ color:var(--ok); } .net-bad{ color:var(--bad); } .net-mid{ color:var(--warn); }

/* شارة التعديلات غير المحفوظة */
.pending{ background:#fff7ed; border:1px solid #fed7aa; color:#9a3412; border-radius:10px; padding:8px 12px; font-weight:700; direction:rtl; }

/* بطاقة المستخدم */
.user-card{ background:var(--primary-soft); border:1px solid #bfdbfe; border-radius:12px; padding:12px; text-align:center; direction:rtl; }
.user-card .u-name{ font-weight:800; color:#1e3a8a; }
.user-card .u-sub{ color:var(--muted); font-size:12px; }
.footer-hint{ font-size:12px; color:var(--muted); margin-top:16px; padding-top:10px; border-top:1px dashed var(--line); line-height:1.8; text-align:right; }

/* أزرار التحميل */
div[data-testid="stDownloadButton"] button{ border-radius:10px !important; font-weight:700 !important; }
div[data-testid="stButton"] button{ border-radius:10px !important; font-weight:700 !important; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# الكوكيز وتسجيل الدخول
# =========================================================
cookies = EncryptedCookieManager(prefix="attendance_app", password="super-secret-password-change-me")

# =========================
# حماية من تعليق الصفحة فاضية للأبد
# =========================
# مكوّن حفظ الكوكيز ده شغال جوه iframe، ولو متصفح المستخدم بيمنع كوكيز/تخزين
# الطرف الثالث (زي إعدادات الخصوصية الحديثة في المتصفحات) المكوّن ده ممكن
# يفضل "not ready" للأبد، والتطبيق كان قبل كده بيعمل st.stop() على طول من غير
# ما يورّي أي حاجة - يعني شاشة فاضية سودة للأبد. دلوقتي بعد كام محاولة (كل
# محاولة كل ثانية تقريبًا) بنكمل تشغيل التطبيق عادي بس من غير خاصية "تذكر
# تسجيل الدخول" (يعني هيطلب تسجيل الدخول تاني لو عملت refresh) بدل ما يفضل
# التطبيق كله متوقف. الطريقة دي مش محتاجة أي جافاسكريبت أو تنقل بين الصفحات:
# st.session_state بيفضل زي ما هو بين كل st.rerun() في نفس الجلسة، فبنعتمد
# عليه بس عشان نعد المحاولات.
COOKIES_MAX_RETRIES = 3

if "cookies_wait_count" not in st.session_state:
    st.session_state["cookies_wait_count"] = 0
if "cookies_unavailable" not in st.session_state:
    st.session_state["cookies_unavailable"] = False

cookies_ready = cookies.ready()

if cookies_ready:
    st.session_state["cookies_wait_count"] = 0

if not cookies_ready and not st.session_state["cookies_unavailable"]:
    st.session_state["cookies_wait_count"] += 1

    if st.session_state["cookies_wait_count"] > COOKIES_MAX_RETRIES:
        st.session_state["cookies_unavailable"] = True
    else:
        st.markdown(
            """
            <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;
                        color:#94a3b8;font-family:sans-serif;direction:rtl;font-size:15px;">
                ⏳ جاري تحميل التطبيق...
            </div>
            """,
            unsafe_allow_html=True,
        )
        time.sleep(1)
        st.rerun()


# =========================
# Session State Init
# =========================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "login_user" not in st.session_state:
    st.session_state["login_user"] = ""

# 🔥 حفظ آخر عملية حذف (Undo)
if "last_deleted_leave" not in st.session_state:
    st.session_state["last_deleted_leave"] = None
# =========================
# Auth helpers
# =========================
def _get_users():
    try:
        return st.secrets.get("app_auth", {}).get("users", [])
    except Exception:
        return [{"username": "admin", "password": "1234"}]


def _check_user(username: str, password: str) -> bool:
    users = _get_users()
    for u in users:
        if u.get("username") == username and u.get("password") == password:
            return True
    return False


def require_login(app_name=" التأخير والغياب والخروج المبكر"):
    use_cookies = not st.session_state.get("cookies_unavailable", False)

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = (use_cookies and cookies.get("logged_in", "") == "true")

    if not st.session_state.get("logged_in", False) and use_cookies:
        st.session_state["logged_in"] = (cookies.get("logged_in", "") == "true")

    if not st.session_state.get("login_user", "") and use_cookies:
        st.session_state["login_user"] = cookies.get("login_user", "")

    if not st.session_state.get("logged_in", False):
        st.markdown(
            """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        .block-container{ max-width: 520px; padding-top: 80px; }
        </style>
        """,
            unsafe_allow_html=True,
        )

        st.markdown(f"## 🔐 {app_name}")
        st.caption("الرجاء تسجيل الدخول للمتابعة")

        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            submit = st.form_submit_button("دخول")

        if submit:
            if _check_user(username.strip(), password):
                st.session_state["logged_in"] = True
                st.session_state["login_user"] = username.strip()

                if use_cookies:
                    cookies["logged_in"] = "true"
                    cookies["login_user"] = username.strip()
                    cookies.save()

                st.rerun()
            else:
                st.error("❌ بيانات الدخول غير صحيحة")

        st.stop()

    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h1 style="margin:0">📊 {app_name}</h1>
            <div style="color:#666;font-weight:700">مرحبًا: {st.session_state.get("login_user", "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "login_user" not in st.session_state:
    st.session_state["login_user"] = ""

require_login("نظام الحضور والإجازات")


# =========================================================
# البيانات الأساسية (بتتقري مرة وتتحفظ في الكاش)
# =========================================================
employees_df = store.employees()
employee_lookup = get_employee_lookup(employees_df)


@st.cache_data(ttl=600, show_spinner=False)
def employee_maps(lookup: pd.DataFrame):
    """قوائم البحث: (الاسم — الرقم) ← الرقم، والرقم ← بيانات الموظف."""
    labels, by_id = {}, {}
    for r in lookup.to_dict("records"):
        eid = fmt_id(r.get("employee_id") or r.get("employee_no"))
        if not eid:
            continue
        labels[f"{safe_str(r.get('name_ar'))} — {eid}"] = eid
        by_id[eid] = r
        no = fmt_id(r.get("employee_no"))
        if no and no not in by_id:
            by_id[no] = r
    return labels, by_id


EMP_LABELS, EMP_BY_ID = employee_maps(employee_lookup)


def build_employee_options() -> dict:
    return EMP_LABELS


def emp_fields(eid: str) -> dict:
    r = EMP_BY_ID.get(fmt_id(eid))
    if not r:
        return {}
    return {
        "employee_id": fmt_id(r.get("employee_id")),
        "employee_no": fmt_id(r.get("employee_no")),
        "name_ar": safe_str(r.get("name_ar")),
        "name_en": safe_str(r.get("name_en")),
        "department": safe_str(r.get("department")),
        "job_title": safe_str(r.get("job_title")),
    }


def fragment(func):
    """تشغيل جزء من الصفحة لوحده (أسرع) لو النسخة بتدعمه."""
    frag = getattr(st, "fragment", None)
    return frag(func) if frag else func


def rerun_fragment():
    try:
        st.rerun(scope="fragment")
    except Exception:
        st.rerun()


def nav(options: list, key: str) -> str:
    """شريط تنقل (أزرار) — بيعرض الصفحة المختارة بس، فالموقع أسرع."""
    ctrl = getattr(st, "segmented_control", None)
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = options[0]
    if ctrl:
        val = ctrl("nav", options, key=key, label_visibility="collapsed")
    else:
        val = st.radio("nav", options, key=key, horizontal=True, label_visibility="collapsed")
    return val or options[0]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# =========================================================
# الشريط الجانبي
# =========================================================
with st.sidebar:
    st.markdown(
        f"""
        <div class="user-card">
            <div style="font-size:28px">👤</div>
            <div class="u-name">{st.session_state.get('login_user', '')}</div>
            <div class="u-sub">مسجّل الدخول</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _ok, _msg = store.status()
    if _ok:
        st.success(f"🟢 {_msg} — الحفظ دائم")
    else:
        st.warning(f"🟡 حفظ مؤقت (محلي) — {_msg}")

    st.markdown("### 📄 ملف البصمة")
    uploaded_file = st.file_uploader("ارفع ملف البصمة (Excel)", type=["xlsx", "xls"], key="att_file")
    s1, s2 = st.columns(2)
    with s1:
        start_time = st.time_input("🕗 بداية الدوام", value=pd.to_datetime("08:00").time(), key="start_time")
    with s2:
        grace = st.number_input("⏱ السماح (دقيقة)", min_value=0, max_value=120, value=15, key="grace")

    st.divider()
    if st.button("🔄 تحديث البيانات", use_container_width=True, key="refresh_btn",
                 help="يقرأ أحدث بيانات من قاعدة البيانات"):
        store.refresh()
        st.rerun()

    if _ok:
        with st.expander("⚙️ نقل البيانات من Google Sheet"):
            st.caption(
                "نزّل الشيت من (ملف ← تنزيل ← Microsoft Excel) وارفعه هنا. الموظفين والإجازات والغياب "
                "هيتنقلوا. السجل الموجود بنفس الرقم بيتحدّث، ومفيش حاجة بتتمسح."
            )
            import_file = st.file_uploader("ملف Excel للشيت", type=["xlsx"], key="sb_import_file")
            if st.button("🔄 نقل البيانات", use_container_width=True, key="sb_import_btn", disabled=import_file is None):
                try:
                    with st.spinner("جاري النقل..."):
                        res = store.import_from_excel(import_file)
                    st.success("✅ تم النقل: " + " | ".join(f"{k}: {v}" for k, v in res.items()))
                except Exception as imp_err:
                    st.error(f"❌ تعذّر النقل: {imp_err}")

    st.markdown(
        """
        <div class="footer-hint">
        🕋 رمضان: 09:30 → 15:30<br>
        🚪 الخروج المبكر: 17:00 (عادي) / 15:30 (رمضان)<br>
        🎉 إجازة العيد لا تُحسب غياب أو تأخير
        </div>
        """,
        unsafe_allow_html=True,
    )
    if os.path.exists(SIDE_IMAGE_PATH):
        st.image(SIDE_IMAGE_PATH, use_container_width=True)

    st.divider()
    if st.button("🚪 تسجيل خروج", use_container_width=True, key="logout_btn"):
        if not st.session_state.get("cookies_unavailable", False):
            cookies["logged_in"] = "false"
            cookies["login_user"] = ""
            cookies.save()
        st.session_state["logged_in"] = False
        st.session_state["login_user"] = ""
        st.rerun()


# =========================================================
# جدول الإدخال والتعديل (مشترك للإجازات والغياب)
# =========================================================
EDITOR_CFG = {
    "leaves": {
        "title": "سجل الإجازات",
        "key": "leave_id",
        "type_col": "leave_type",
        "type_options": LEAVE_TYPES,
        "text_col": "notes",
        "text_label": "ملاحظات",
        "folder": "leaves",
    },
    "absences": {
        "title": "سجل الغياب والتأخير",
        "key": "record_id",
        "type_col": "record_type",
        "type_options": ABSENCE_TYPES,
        "text_col": "reason",
        "text_label": "السبب",
        "folder": "absences",
    },
}
EDIT_COLS = ["employee_id", "TYPE", "start_date", "end_date", "TEXT"]


def _editor_state(kind: str):
    ss = st.session_state
    ss.setdefault(f"{kind}_ver", 0)
    return ss


def _display_frame(kind: str, data: pd.DataFrame) -> pd.DataFrame:
    cfg = EDITOR_CFG[kind]
    d = pd.DataFrame({
        "id": data[cfg["key"]],
        "employee_id": data["employee_id"],
        "name_ar": data["name_ar"],
        "department": data["department"],
        "TYPE": data[cfg["type_col"]],
        "start_date": pd.to_datetime(data["start_date"], errors="coerce").dt.date,
        "end_date": pd.to_datetime(data["end_date"], errors="coerce").dt.date,
        "days": [leave_days_count(s, e) for s, e in zip(data["start_date"], data["end_date"])],
        "TEXT": data[cfg["text_col"]],
        "att": data["attachment_name"].apply(lambda v: "📎" if safe_str(v) else ""),
    })
    return d.reset_index(drop=True)


def _collect_changes(kind: str, view: pd.DataFrame, delta: dict):
    """يحوّل تعديلات الجدول لـ (إضافات، تعديلات، حذف، أخطاء)."""
    cfg = EDITOR_CFG[kind]
    user = st.session_state.get("login_user", "")
    inserts, updates, deletes, errors = [], {}, [], []

    def conv(col, val):
        if col in ("start_date", "end_date"):
            ts = pd.to_datetime(val, errors="coerce")
            return None if pd.isna(ts) else ts.normalize()
        if col == "employee_id":
            return fmt_id(val)
        return safe_str(val)

    real = {"TYPE": cfg["type_col"], "TEXT": cfg["text_col"]}

    # تعديل صفوف موجودة
    for idx, changes in (delta.get("edited_rows") or {}).items():
        idx = int(idx)
        if idx >= len(view):
            continue
        row = view.iloc[idx]
        rid = row["id"]
        fields = {}
        for col, val in changes.items():
            if col not in EDIT_COLS:
                continue
            fields[real.get(col, col)] = conv(col, val)
        if "employee_id" in fields:
            ef = emp_fields(fields["employee_id"])
            if not ef:
                errors.append(f"الصف {idx + 1}: الرقم الوظيفي {fields['employee_id']} غير موجود")
                continue
            fields.update({k: v for k, v in ef.items() if k in store.KINDS[kind]["cols"]})
        s = fields.get("start_date", pd.to_datetime(row["start_date"]))
        e = fields.get("end_date", pd.to_datetime(row["end_date"]))
        if s is None:
            errors.append(f"الصف {idx + 1}: تاريخ البداية مطلوب")
            continue
        if e is not None and pd.notna(s) and e < s:
            errors.append(f"الصف {idx + 1}: تاريخ النهاية قبل البداية")
            continue
        if fields:
            updates[rid] = fields

    # حذف
    for idx in delta.get("deleted_rows") or []:
        if int(idx) < len(view):
            deletes.append(view.iloc[int(idx)]["id"])

    # إضافة صفوف جديدة
    for n, added in enumerate(delta.get("added_rows") or [], start=1):
        if not any(safe_str(v) for v in added.values()):
            continue
        eid = conv("employee_id", added.get("employee_id"))
        ef = emp_fields(eid)
        if not ef:
            errors.append(f"صف جديد {n}: اكتب رقم وظيفي صحيح" + (f" ({eid} غير موجود)" if eid else ""))
            continue
        s = conv("start_date", added.get("start_date"))
        e = conv("end_date", added.get("end_date")) or s
        if s is None:
            errors.append(f"صف جديد {n} ({ef['name_ar']}): تاريخ البداية مطلوب")
            continue
        if e < s:
            errors.append(f"صف جديد {n} ({ef['name_ar']}): تاريخ النهاية قبل البداية")
            continue
        rec = {k: v for k, v in ef.items() if k in store.KINDS[kind]["cols"]}
        rec.update({
            cfg["type_col"]: safe_str(added.get("TYPE")) or cfg["type_options"][0],
            "start_date": s,
            "end_date": e,
            cfg["text_col"]: safe_str(added.get("TEXT")),
            "created_by": user,
        })
        if kind == "leaves":
            rec["status"] = "معتمدة"
        inserts.append(rec)

    return inserts, updates, deletes, errors


@fragment
def records_page(kind: str):
    cfg = EDITOR_CFG[kind]
    ss = _editor_state(kind)
    user = ss.get("login_user", "")

    # ---------------- إضافة سريعة ----------------
    with st.container(border=True):
        st.markdown(f"**➕ إضافة سريعة — {cfg['title']}**")
        with st.form(f"{kind}_quick_form", clear_on_submit=True):
            q1, q2, q3, q4 = st.columns([3, 1.4, 1.2, 1.2])
            with q1:
                q_emp = st.selectbox("🔎 الموظف (اكتب الاسم أو الرقم الوظيفي)", list(EMP_LABELS.keys()),
                                     index=None, placeholder="اكتب جزء من الاسم أو الرقم...")
            with q2:
                q_type = st.selectbox("النوع", cfg["type_options"])
            with q3:
                q_from = st.date_input("من", value=dt.date.today())
            with q4:
                q_to = st.date_input("إلى", value=dt.date.today())
            t1, t2 = st.columns([3, 2])
            with t1:
                if kind == "absences":
                    r1, r2 = st.columns(2)
                    q_pick = r1.selectbox("سبب مقترح", ["— اختر —"] + ABSENCE_REASONS)
                    q_text = r2.text_input("أو اكتب السبب")
                else:
                    q_pick = "— اختر —"
                    q_text = st.text_input("ملاحظات")
            with t2:
                q_file = st.file_uploader("مرفق (اختياري)", type=["pdf", "png", "jpg", "jpeg", "doc", "docx"])
            q_submit = st.form_submit_button("💾 حفظ", type="primary", use_container_width=True)

        if q_submit:
            text = q_text.strip() or (q_pick if q_pick != "— اختر —" else "")
            if not q_emp:
                st.error("اختر الموظف أولاً")
            elif q_to < q_from:
                st.error("تاريخ النهاية قبل البداية")
            elif kind == "absences" and q_type == "أخرى" and not text:
                st.error("اكتب السبب عند اختيار (أخرى)")
            else:
                ef = emp_fields(EMP_LABELS[q_emp])
                try:
                    att_name, att_path = store.upload_attachment(q_file, cfg["folder"], ef["employee_id"])
                    rec = {k: v for k, v in ef.items() if k in store.KINDS[kind]["cols"]}
                    rec.update({
                        cfg["type_col"]: q_type, "start_date": pd.Timestamp(q_from), "end_date": pd.Timestamp(q_to),
                        cfg["text_col"]: text, "attachment_name": att_name, "attachment_path": att_path,
                        "created_by": user,
                    })
                    if kind == "leaves":
                        rec["status"] = "معتمدة"
                    store.apply_changes(kind, [rec], {}, [])
                    st.toast(f"✅ تم حفظ ({q_type}) لـ {ef['name_ar']} — {leave_days_count(q_from, q_to)} يوم")
                    ss[f"{kind}_ver"] += 1
                    rerun_fragment()
                except Exception as e:
                    st.error(f"❌ تعذّر الحفظ: {e}")

    # ---------------- الفلاتر ----------------
    data = store.load(kind)
    f1, f2, f3, f4 = st.columns([1, 1, 2, 2])
    with f1:
        d_from = st.date_input("من تاريخ", value=dt.date.today() - dt.timedelta(days=90), key=f"{kind}_f_from")
    with f2:
        d_to = st.date_input("إلى تاريخ", value=dt.date.today() + dt.timedelta(days=60), key=f"{kind}_f_to")
    with f3:
        q = st.text_input("🔎 بحث بالاسم أو الرقم الوظيفي", key=f"{kind}_f_q", placeholder="مثال: 27164 أو محمد")
    with f4:
        types = st.multiselect("النوع", cfg["type_options"], key=f"{kind}_f_types", placeholder="كل الأنواع")

    view_src = data[(data["end_date"] >= pd.Timestamp(d_from)) & (data["start_date"] <= pd.Timestamp(d_to))]
    if q.strip():
        qq = q.strip()
        view_src = view_src[view_src["employee_id"].str.contains(qq, regex=False) |
                            view_src["name_ar"].str.contains(qq, regex=False)]
    if types:
        view_src = view_src[view_src[cfg["type_col"]].isin(types)]
    view_src = view_src.sort_values(["start_date", cfg["key"]], ascending=[False, False])
    view = _display_frame(kind, view_src)

    # ---------------- الجدول ----------------
    sig = f"{d_from}|{d_to}|{q}|{','.join(types)}"
    ed_key = f"{kind}_ed_{ss[f'{kind}_ver']}_{zlib.crc32(sig.encode())}"

    st.markdown(
        f'<div class="hint">✏️ عدّل في الخانات مباشرة، أو أضف صف جديد من آخر الجدول (اكتب الرقم الوظيفي والاسم هيتعبّى عند الحفظ)، '
        f'أو حدد صف واضغط 🗑️ لحذفه. التعديلات ما بتتحفظش غير لما تضغط <b>💾 حفظ التغييرات</b>. '
        f'المعروض: <b>{len(view)}</b> سجل.</div>',
        unsafe_allow_html=True,
    )

    st.data_editor(
        view,
        key=ed_key,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        height=min(560, 38 + 35 * (len(view) + 2)),
        column_order=["id", "employee_id", "name_ar", "department", "TYPE", "start_date", "end_date", "days", "TEXT", "att"],
        column_config={
            "id": st.column_config.TextColumn("رقم السجل", disabled=True, width="small"),
            "employee_id": st.column_config.TextColumn("الرقم الوظيفي", required=True, width="small"),
            "name_ar": st.column_config.TextColumn("الاسم", disabled=True, width="medium"),
            "department": st.column_config.TextColumn("القسم", disabled=True, width="small"),
            "TYPE": st.column_config.SelectboxColumn("النوع", options=cfg["type_options"], required=True, width="small"),
            "start_date": st.column_config.DateColumn("من", format="YYYY/MM/DD", required=True, width="small"),
            "end_date": st.column_config.DateColumn("إلى", format="YYYY/MM/DD", width="small"),
            "days": st.column_config.NumberColumn("الأيام", disabled=True, width="small"),
            "TEXT": st.column_config.TextColumn(cfg["text_label"], width="large"),
            "att": st.column_config.TextColumn("📎", disabled=True, width="small"),
        },
    )

    delta = ss.get(ed_key) or {}
    inserts, updates, deletes, errors = _collect_changes(kind, view, delta)
    has_changes = bool(inserts or updates or deletes or errors)

    b1, b2, b3 = st.columns([2, 1, 1])
    with b1:
        if has_changes:
            st.markdown(
                f'<div class="pending">تعديلات غير محفوظة: ➕ {len(inserts)} جديد &nbsp; ✏️ {len(updates)} تعديل '
                f'&nbsp; 🗑️ {len(deletes)} حذف</div>',
                unsafe_allow_html=True,
            )
        for err in errors:
            st.error(err)
        if inserts:
            st.caption("الجديد: " + "، ".join(f"{r['name_ar']} ({r['employee_id']})" for r in inserts))
    with b2:
        save = st.button("💾 حفظ التغييرات", type="primary", use_container_width=True,
                         disabled=not (inserts or updates or deletes) or bool(errors), key=f"{kind}_save")
    with b3:
        undo = st.button("↩️ إلغاء التعديلات", use_container_width=True, disabled=not has_changes, key=f"{kind}_undo")

    if save:
        try:
            with st.spinner("جاري الحفظ..."):
                res = store.apply_changes(kind, inserts, updates, deletes)
            st.toast(f"✅ تم الحفظ — جديد {res['added']} | تعديل {res['updated']} | حذف {res['deleted']}")
            ss[f"{kind}_ver"] += 1
            rerun_fragment()
        except Exception as e:
            st.error(f"❌ تعذّر الحفظ: {e}")
    if undo:
        ss[f"{kind}_ver"] += 1
        rerun_fragment()

    # ---------------- تصدير + مرفقات ----------------
    e1, e2 = st.columns([1, 2])
    with e1:
        st.download_button(
            "📥 تصدير المعروض Excel",
            data=to_excel_bytes(view_src),
            file_name=f"{kind}_{d_from}_{d_to}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"{kind}_xlsx",
        )
    with e2:
        with st.expander("📎 المرفقات (عرض / إضافة / استبدال)"):
            if view_src.empty:
                st.caption("لا توجد سجلات معروضة.")
            else:
                opts = {
                    f"{r[cfg['key']]} | {r['name_ar']} | {r[cfg['type_col']]} | {fmt_date(r['start_date'])}"
                    + (" 📎" if safe_str(r["attachment_name"]) else ""): r
                    for r in view_src.to_dict("records")
                }
                pick = st.selectbox("السجل", list(opts.keys()), index=None, key=f"{kind}_att_pick")
                if pick:
                    r = opts[pick]
                    path = safe_str(r.get("attachment_path"))
                    if store.attachment_available(path):
                        try:
                            data_b = store.read_attachment(path)
                            if path.lower().endswith((".png", ".jpg", ".jpeg")):
                                st.image(data_b, use_container_width=True)
                            st.download_button("⬇️ تحميل المرفق", data=data_b,
                                               file_name=safe_str(r.get("attachment_name")) or "attachment",
                                               key=f"{kind}_att_dl")
                        except Exception as e:
                            st.error(f"تعذّر فتح المرفق: {e}")
                    else:
                        st.caption("لا يوجد مرفق لهذا السجل.")
                    new_file = st.file_uploader("إرفاق / استبدال الملف", type=["pdf", "png", "jpg", "jpeg", "doc", "docx"],
                                                key=f"{kind}_att_up")
                    if new_file is not None and st.button("💾 حفظ المرفق", key=f"{kind}_att_save"):
                        try:
                            n, p = store.upload_attachment(new_file, cfg["folder"], r["employee_id"])
                            store.apply_changes(kind, [], {r[cfg["key"]]: {"attachment_name": n, "attachment_path": p}}, [])
                            st.toast("✅ تم حفظ المرفق")
                            ss[f"{kind}_ver"] += 1
                            rerun_fragment()
                        except Exception as e:
                            st.error(f"❌ تعذّر حفظ المرفق: {e}")


# =========================================================
# تقرير البصمة
# =========================================================
@st.cache_data(show_spinner="جاري قراءة ملف البصمة...", max_entries=5)
def run_attendance(file_bytes: bytes, start_time, grace_minutes, schedule_mode, employees_df, daily_required_hours, approved_leaves_df):
    return process_attendance(
        BytesIO(file_bytes),
        start_time=start_time,
        grace_minutes=grace_minutes,
        schedule_mode=schedule_mode,
        employees_df=employees_df,
        daily_required_hours=daily_required_hours,
        approved_leaves_df=approved_leaves_df,
    )


@st.cache_data(show_spinner=False, max_entries=20)
def cached_pdf(emp, late_emp, abs_emp, leave_emp, lang="ar", excuses_df=None):
    return build_pdf(emp, late_emp, abs_emp, leave_emp, lang=lang, excuses_df=excuses_df)


def page_attendance():
    leaves_df = store.load("leaves")
    if not uploaded_file:
        st.markdown(
            """
            <div class="hero-card">
              <div class="hero-title">📊 لوحة تقرير البصمة</div>
              <div class="hero-sub">ارفع ملف البصمة من القائمة الجانبية لعرض التقرير الكامل: التأخير، الخروج المبكر، الغياب (بإذن / بدون إذن)، والإجازات المعتمدة.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        a1, a2, a3 = st.columns(3)
        a1.markdown('<div class="grid-note">⏱ احتساب التأخير يتم تلقائيًا حسب وقت البداية + السماح.</div>', unsafe_allow_html=True)
        a2.markdown('<div class="grid-note">📝 الغياب المسجّل "بإذن" يظهر مميّزًا في التقرير وملف PDF.</div>', unsafe_allow_html=True)
        a3.markdown('<div class="grid-note">🏖️ الإجازات المعتمدة تُستبعد من الغياب تلقائيًا.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="grid-note" style="margin-top:10px">{eid_al_adha_hint()}</div>', unsafe_allow_html=True)
    else:
        try:
            summary, late, absence, exempt_report, approved_leave_days = run_attendance(
                uploaded_file.getvalue(),
                start_time=start_time.strftime("%H:%M"),
                grace_minutes=int(grace),
                schedule_mode="by_nationality",
                employees_df=employees_df,
                daily_required_hours=9.0,
                approved_leaves_df=leaves_df,
            )
            summary, absence = exclude_eid_al_adha_absence(summary, absence)
        except Exception as proc_err:
            st.error(f"❌ تعذّر قراءة ملف البصمة: {proc_err}")
            summary = None

        if summary is None or summary.empty:
            st.error("لا توجد بيانات بعد المعالجة.")
        elif len(summary) != 1:
            st.warning("الملف يحتوي أكثر من موظف — هذا العرض مصمم لموظف واحد حاليًا.")
            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            emp = summary.iloc[0]
            emp_personnel_id = safe_str(emp.get("employee_id", ""))
            emp_no = fmt_id(emp.get("employee_no", ""))
            name_ar = safe_str(emp.get("name_ar", ""))
            name_en = safe_str(emp.get("name_en", ""))
            nat = safe_str(emp.get("nationality", emp.get("nationality_raw", "")))
            dept = safe_str(emp.get("department", ""))
            job = safe_str(emp.get("job_title", ""))
            period_from = emp.get("period_from")
            period_to = emp.get("period_to")

            def _filter_emp(df_):
                if df_ is None or df_.empty:
                    return pd.DataFrame()
                return df_[df_["employee_id"].astype(str).str.strip() == emp_personnel_id].copy()

            late_emp = _filter_emp(late)
            abs_emp = _filter_emp(absence)
            leave_emp = _filter_emp(approved_leave_days)

            for _df in (late_emp, abs_emp, leave_emp):
                if not _df.empty and "weekday" in _df.columns:
                    _df["weekday_ar"] = _df["weekday"].apply(weekday_to_ar)

            # ربط الغياب/التأخير بالأعذار المسجلة في تبويب "تسجيل غياب / تأخير"
            all_abs_records = store.load("absences")
            emp_records = absence_records_for_employee(
                all_abs_records, emp_personnel_id, period_from, period_to
            )
            if emp_records.empty and emp_no and emp_no != emp_personnel_id:
                emp_records = absence_records_for_employee(
                    all_abs_records, emp_no, period_from, period_to
                )
            abs_emp = annotate_absence_days(abs_emp, emp_records)
            late_emp = annotate_late_days(late_emp, emp_records)

            excused_days = int((abs_emp["absence_type"] == "غياب بإذن").sum()) if not abs_emp.empty else 0
            unexcused_days = (len(abs_emp) - excused_days) if not abs_emp.empty else 0

            pdf_ar = cached_pdf(emp, late_emp, abs_emp, leave_emp, lang="ar", excuses_df=emp_records)
            pdf_en = cached_pdf(emp, late_emp, abs_emp, leave_emp, lang="en", excuses_df=emp_records)
            base_name = sanitize_filename(name_ar or name_en)
            base_no = sanitize_filename(emp_no)

            # ---------- بطاقة الموظف ----------
            st.markdown(
                '<div class="step-title">📌 نتيجة التقرير</div>',
                unsafe_allow_html=True,
            )
            title = month_year_title(emp)
            schedule = safe_str(emp.get("schedule", ""))
            sat_note = "✅ دوام السبت" if schedule == "جمعة فقط" else "🛑 إجازة السبت"

            h1, h2 = st.columns([3, 1])
            with h1:
                st.markdown(
                    f"""
                    <div class="hero-card">
                    <div class="hero-title">{title}</div>
                    <div class="hero-sub">🛑 إجازة الجمعة • {sat_note} • الفترة: {fmt_date(period_from)} → {fmt_date(period_to)}</div>
                    <div style="font-size:26px;font-weight:900;margin-top:10px">👤 {name_ar}</div>
                    <div class="hero-sub">{name_en}</div>
                    <div class="hero-sub" style="margin-top:4px">{nat} • {job} • {dept}</div>
                    <div style="margin-top:8px;font-weight:800">الكود / الرقم الوظيفي: {emp_no}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with h2:
                st.markdown("**⬇️ تصدير التقرير**")
                st.download_button(
                    "📄 PDF عربي",
                    data=pdf_ar,
                    file_name=f"{base_name}_{base_no}_AR.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="download_pdf_ar",
                )
                st.download_button(
                    "📄 PDF English",
                    data=pdf_en,
                    file_name=f"{base_name}_{base_no}_EN.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="download_pdf_en",
                )

            # ---------- المؤشرات ----------
            def _kpi(col, value, label):
                col.markdown(
                    f'<div class="small-kpi"><div class="n">{value}</div><div class="t">{label}</div></div>',
                    unsafe_allow_html=True,
                )

            k1, k2, k3, k4 = st.columns(4)
            _kpi(k1, int(emp.get("late_days", 0) or 0), "أيام التأخير")
            _kpi(k2, mm_to_hhmm(int(emp.get("total_late_minutes", 0) or 0)), "إجمالي التأخير")
            _kpi(k3, int(emp.get("early_leave_days", 0) or 0), "أيام الخروج المبكر")
            _kpi(k4, mm_to_hhmm(int(emp.get("total_early_leave_minutes", 0) or 0)), "إجمالي الخروج المبكر")

            st.write("")
            k5, k6, k7, k8 = st.columns(4)
            _kpi(k5, int(emp.get("absent_days", 0) or 0), "إجمالي أيام الغياب")
            _kpi(k6, excused_days, "✅ غياب بإذن")
            _kpi(k7, unexcused_days, "🚫 غياب بدون إذن")
            _kpi(k8, int(emp.get("approved_leave_days", 0) or 0), "🏖️ إجازات معتمدة")
            st.write("")

            attendance_rule = safe_str(emp.get("attendance_calculation", "")).strip().lower()
            total_late = int(emp.get("total_late_minutes", 0) or 0)
            total_early_leave = int(emp.get("total_early_leave_minutes", 0) or 0)
            total_deficit = total_late + total_early_leave
            if attendance_rule == "daily_hours":
                total_overtime = int(emp.get("total_overtime_minutes", 0) or 0)
                net = total_overtime - total_deficit
                net_label = "صافي إضافي" if net > 0 else ("صافي عجز" if net < 0 else "متعادل")
                net_class = "net-good" if net > 0 else ("net-bad" if net < 0 else "net-mid")
                st.markdown(
                    f"""
                    <div class="net-box">
                      <div class="net-title">🧾 نتيجة الاحتساب للمستثنى</div>
                      <div class="net-big {net_class}">{net_label}: {mm_to_hhmm(net)}</div>
                      <div class="net-sub">الصافي = إجمالي الإضافي − (إجمالي التأخير + إجمالي الخروج المبكر)</div>
                      <div class="net-row">
                        <div class="net-pill">⬇️ التأخير: <b>{mm_to_hhmm(total_late)}</b></div>
                        <div class="net-pill">🚪 الخروج المبكر: <b>{mm_to_hhmm(total_early_leave)}</b></div>
                        <div class="net-pill">⬆️ الإضافي: <b>{mm_to_hhmm(total_overtime)}</b></div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="net-box">
                      <div class="net-title">🧾 ملخص الاحتساب</div>
                      <div class="net-big net-bad">إجمالي التأخيرات: {mm_to_hhmm(total_deficit)}</div>
                      <div class="net-sub">إجمالي التأخيرات = التأخير + الخروج المبكر</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.write("")
            details_tab, status_tab = st.tabs(["🧾 التفاصيل اليومية", "🚫 الغياب والإجازات"])

            # ---------- التفاصيل اليومية ----------
            with details_tab:
                if late_emp is None or late_emp.empty:
                    st.success("لا يوجد سجلات تأخير أو خروج مبكر ✅")
                else:
                    d = late_emp.copy()
                    d["date"] = pd.to_datetime(d["date"], errors="coerce")
                    d = d.sort_values("date")

                    def _hm(x):
                        tt = pd.to_datetime(str(x), errors="coerce") if safe_str(x) else pd.NaT
                        return "" if pd.isna(tt) else tt.strftime("%H:%M")

                    d["اليوم"] = d.get("weekday_ar", "").apply(safe_str) if "weekday_ar" in d.columns else ""
                    d["التاريخ"] = d["date"].apply(fmt_date)
                    d["أول بصمة"] = d["first_punch_time"].apply(_hm) if "first_punch_time" in d.columns else ""
                    d["آخر بصمة"] = d["last_punch_time"].apply(_hm) if "last_punch_time" in d.columns else ""
                    d["التأخير"] = d["late_minutes"].apply(mm_to_hhmm)
                    d["الخروج المبكر"] = d["early_leave_minutes"].apply(mm_to_hhmm)
                    d["العذر"] = d["excuse"].apply(lambda v: safe_str(v) or "—") if "excuse" in d.columns else "—"

                    show_cols = ["اليوم", "التاريخ", "أول بصمة", "آخر بصمة", "التأخير", "الخروج المبكر"]
                    if attendance_rule == "daily_hours":
                        if "worked_minutes" in d.columns:
                            d["ساعات العمل"] = d["worked_minutes"].apply(mm_to_hhmm)
                            show_cols.insert(4, "ساعات العمل")
                        if "overtime_minutes" in d.columns:
                            d["الإضافي"] = d["overtime_minutes"].apply(mm_to_hhmm)
                            show_cols.append("الإضافي")
                    show_cols.append("العذر")
                    st.dataframe(d[show_cols], use_container_width=True, hide_index=True)

            # ---------- الغياب والإجازات ----------
            with status_tab:
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.markdown("##### 🚫 أيام الغياب")
                    if abs_emp.empty:
                        st.success("لا يوجد غياب ✅")
                    else:
                        a = abs_emp.copy()
                        a["اليوم"] = a["weekday_ar"].apply(safe_str) if "weekday_ar" in a.columns else ""
                        a["التاريخ"] = a["date"].apply(fmt_date)
                        a["النوع"] = a["absence_type"]
                        a["السبب"] = a["absence_reason"].apply(lambda v: safe_str(v) or "—")
                        st.dataframe(a[["اليوم", "التاريخ", "النوع", "السبب"]], use_container_width=True, hide_index=True)

                with sc2:
                    st.markdown("##### 🏖️ الإجازات المعتمدة")
                    if leave_emp.empty:
                        st.success("لا توجد إجازات معتمدة ضمن الفترة ✅")
                    else:
                        lv = leave_emp.copy()
                        lv["اليوم"] = lv["weekday_ar"].apply(safe_str) if "weekday_ar" in lv.columns else ""
                        lv["التاريخ"] = lv["date"].apply(fmt_date)
                        lv["نوع الإجازة"] = lv["leave_type"].apply(safe_str) if "leave_type" in lv.columns else ""
                        st.dataframe(lv[["اليوم", "التاريخ", "نوع الإجازة"]], use_container_width=True, hide_index=True)

                if not abs_emp.empty and (abs_emp["absence_type"] == "غياب بدون إذن (غير مسجل)").any():
                    st.caption("ℹ️ لتحديد نوع أيام الغياب غير المسجلة، سجّلها من تبويب (📝 تسجيل غياب / تأخير).")


# =========================================================
# التقارير
# =========================================================
def render_leave_results_table(res: pd.DataFrame):
    display_df = res.copy()
    display_df["من"] = display_df["start_date"].apply(fmt_date)
    display_df["إلى"] = display_df["end_date"].apply(fmt_date)
    display_df["الموظف"] = display_df["name_ar"].apply(safe_str)
    display_df["الرقم الوظيفي"] = display_df["employee_no"].apply(fmt_id)
    display_df["النوع"] = display_df["leave_type"].apply(safe_str)
    display_df["عدد الأيام"] = display_df.apply(
        lambda r: leave_days_count(r.get("start_date"), r.get("end_date")), axis=1
    )
    display_df["الحالة"] = display_df["status"].apply(safe_str)
    display_df["ملاحظات"] = display_df["notes"].apply(safe_str)

    table_df = display_df[[
        "الموظف",
        "الرقم الوظيفي",
        "النوع",
        "من",
        "إلى",
        "عدد الأيام",
        "الحالة",
        "ملاحظات",
    ]].reset_index(drop=True)

    st.dataframe(table_df, use_container_width=True, hide_index=True)


def render_leave_totals(res: pd.DataFrame, employee_name: str = ""):
    """
    بطاقة إجماليات لتقرير إجازات الموظف: اسم الموظف (لو محدد)، عدد الإجازات،
    إجمالي الأيام، وتوزيع الأيام حسب نوع الإجازة.
    """
    x = res.copy()
    x["_days"] = x.apply(
        lambda r: leave_days_count(r.get("start_date"), r.get("end_date")), axis=1
    )

    total_records = len(x)
    total_days = int(x["_days"].sum())

    if employee_name:
        st.markdown(f"#### 👤 {employee_name}")

    m1, m2 = st.columns(2)
    m1.markdown(
        f'<div class="small-kpi"><div class="n">{total_records}</div><div class="t">📄 عدد الإجازات</div></div>',
        unsafe_allow_html=True,
    )
    m2.markdown(
        f'<div class="small-kpi"><div class="n">{total_days}</div><div class="t">📅 إجمالي أيام الإجازات</div></div>',
        unsafe_allow_html=True,
    )

    breakdown = (
        x.assign(leave_type=x["leave_type"].apply(lambda v: safe_str(v) or "غير محدد"))
        .groupby("leave_type")["_days"]
        .sum()
        .sort_values(ascending=False)
    )

    if not breakdown.empty:
        st.markdown("**تفصيل حسب نوع الإجازة:**")
        b_cols = st.columns(min(len(breakdown), 6))
        for i, (k, v) in enumerate(breakdown.items()):
            with b_cols[i % len(b_cols)]:
                st.markdown(
                    f'<div class="small-kpi"><div class="n">{int(v)}</div><div class="t">{safe_str(k)}</div></div>',
                    unsafe_allow_html=True,
                )


def page_emp_report():
    st.markdown('<div class="card"><div class="card-title">📄 تقرير الموظف</div>', unsafe_allow_html=True)

    if employee_lookup.empty:
        st.info("ملف الموظفين غير متوفر.")
    else:
        options_map_er = {
            employee_option_label(r): (r.get("employee_id") or r.get("employee_no"))
            for _, r in employee_lookup.iterrows()
        }

        # ملحوظة أداء: العناصر دي متحطة جوه st.form عشان اختيار الموظف أو
        # تغيير التاريخ ما يعملوش إعادة تحميل للصفحة كلها في كل مرة. البرنامج
        # ميبدأش يجمّع ويجهّز التقرير إلا لما تدخل كل البيانات وتضغط زرار
        # "عرض التقرير" (أو "مسح") - فمفيش انتظار غير مرة واحدة بس عند الضغط.
        with st.form("emp_report_form"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                er_selected_emp = st.selectbox(
                    "اختر الموظف",
                    options=list(options_map_er.keys()),
                    index=None,
                    placeholder="ابحث باسم الموظف...",
                    key="emp_report_selected_emp",
                )
            with c2:
                er_from = st.date_input(
                    "من تاريخ",
                    value=dt.date(dt.date.today().year, 1, 1),
                    key="emp_report_from",
                )
            with c3:
                er_to = st.date_input("إلى تاريخ", key="emp_report_to")

            btn1, btn2 = st.columns(2)
            with btn1:
                er_show_clicked = st.form_submit_button("📄 عرض التقرير", use_container_width=True)
            with btn2:
                er_clear_clicked = st.form_submit_button("🧹 مسح", use_container_width=True)

        er_selected_key = str(options_map_er[er_selected_emp]) if er_selected_emp else ""

        if "emp_report_show_result" not in st.session_state:
            st.session_state["emp_report_show_result"] = False
        if "emp_report_result_df" not in st.session_state:
            st.session_state["emp_report_result_df"] = pd.DataFrame()

        if er_clear_clicked:
            st.session_state["emp_report_show_result"] = False
            st.session_state["emp_report_result_df"] = pd.DataFrame()
            st.rerun()

        if er_show_clicked:
            if not er_selected_emp:
                st.warning("اختر الموظف أولاً")
                st.session_state["emp_report_show_result"] = False
            else:
                df = store.load("leaves").copy()
                if df.empty:
                    st.session_state["emp_report_show_result"] = True
                    st.session_state["emp_report_result_df"] = pd.DataFrame()
                else:
                    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
                    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

                    df = df[
                        (df["employee_id"].astype(str).str.strip() == er_selected_key.strip()) |
                        (df["employee_no"].astype(str).str.strip() == er_selected_key.strip())
                    ]
                    mask = (df["start_date"] <= pd.to_datetime(er_to)) & (df["end_date"] >= pd.to_datetime(er_from))
                    st.session_state["emp_report_result_df"] = df[mask].sort_values(
                        ["start_date", "end_date"], ascending=[False, False]
                    ).copy()
                    st.session_state["emp_report_show_result"] = True

        if st.session_state.get("emp_report_show_result", False):
            res = st.session_state.get("emp_report_result_df", pd.DataFrame())

            if res is None or res.empty:
                st.info("لا توجد إجازات لهذا الموظف ضمن الفترة المحددة.")
            else:
                st.write(f"عدد السجلات: {len(res)}")
                render_leave_results_table(res)

                st.markdown("---")
                st.markdown("### 📊 تقرير إجازات الموظف")
                emp_name_for_totals = safe_str(res["name_ar"].iloc[0]) if "name_ar" in res.columns else ""
                render_leave_totals(res, employee_name=emp_name_for_totals)

                pdf_bytes = build_leaves_pdf(res)
                pdf_name = f"leave_report_{sanitize_filename(er_selected_key)}.pdf"

                st.download_button(
                    label="📄 تصدير تقرير الموظف PDF",
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    use_container_width=True,
                    key="emp_report_pdf_download_btn",
                )

    st.markdown("</div>", unsafe_allow_html=True)


def page_sick():
    st.markdown(
        '<div class="card"><div class="card-title">🤒 تقرير الإجازات المرضية حسب الموظف</div>',
        unsafe_allow_html=True
    )

    all_leaves_sick = store.load("leaves")

    if all_leaves_sick.empty or "leave_type" not in all_leaves_sick.columns:
        st.info("لا توجد بيانات إجازات بعد.")
    else:
        default_from = dt.date(2026, 1, 1)
        default_to = dt.date.today()

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            sick_date_from = st.date_input(
                "من تاريخ",
                value=default_from,
                key="sick_leave_date_from"
            )
        with c2:
            sick_date_to = st.date_input(
                "إلى تاريخ",
                value=default_to,
                key="sick_leave_date_to"
            )
        with c3:
            st.caption(f"🔴 الحد السنوي المسموح به لكل موظف: {SICK_LEAVE_ANNUAL_QUOTA} يوم")

        if sick_date_to < sick_date_from:
            st.error("تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية")
            summary_df = pd.DataFrame()
        else:
            summary_df = compute_sick_leave_summary(
                all_leaves_sick,
                date_from=sick_date_from,
                date_to=sick_date_to,
            )

        period_label = f"{fmt_date(sick_date_from)} → {fmt_date(sick_date_to)}"

        if summary_df.empty:
            st.info("لا توجد إجازات مرضية مسجلة ضمن الفترة المحددة.")
        else:
            total_employees = len(summary_df)
            exceeded_count = int((summary_df["total_days"] >= SICK_LEAVE_ANNUAL_QUOTA).sum())
            near_limit_count = int(
                ((summary_df["total_days"] >= SICK_LEAVE_ANNUAL_QUOTA * 0.7) &
                 (summary_df["total_days"] < SICK_LEAVE_ANNUAL_QUOTA)).sum()
            )
            total_days_all = int(summary_df["total_days"].sum())

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("👥 عدد الموظفين", total_employees)
            m2.metric("📅 إجمالي أيام الإجازات المرضية", total_days_all)
            m3.metric("🟡 اقتربوا من الحد", near_limit_count)
            m4.metric("🔴 تجاوزوا الحد السنوي", exceeded_count)

            if exceeded_count > 0:
                st.error(
                    f"⚠️ يوجد {exceeded_count} موظف تجاوز الحد السنوي المسموح به ({SICK_LEAVE_ANNUAL_QUOTA} يوم) "
                    f"من الإجازات المرضية."
                )

            display_df = summary_df.copy()
            display_df["الترتيب"] = display_df["rank"]
            display_df["الموظف"] = display_df["name_ar"]
            display_df["الرقم الوظيفي"] = display_df["employee_no"].apply(fmt_id)
            display_df["القسم"] = display_df["department"]
            display_df["عدد الإجازات"] = display_df["leave_count"]
            display_df["إجمالي الأيام"] = display_df["total_days"]
            display_df["المتبقي من الحد"] = display_df["remaining_days"]
            display_df["آخر إجازة"] = display_df["last_leave_date"].apply(fmt_date)
            display_df["المؤشر"] = display_df["status"]

            table_df = display_df[[
                "الترتيب",
                "الموظف",
                "الرقم الوظيفي",
                "القسم",
                "عدد الإجازات",
                "إجمالي الأيام",
                "المتبقي من الحد",
                "آخر إجازة",
                "المؤشر",
            ]].reset_index(drop=True)

            st.dataframe(
                table_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "إجمالي الأيام": st.column_config.ProgressColumn(
                        "إجمالي الأيام",
                        min_value=0,
                        max_value=max(SICK_LEAVE_ANNUAL_QUOTA, int(summary_df["total_days"].max())),
                        format="%d",
                    ),
                },
            )

            st.markdown("### 📌 تفاصيل الموظفين المتجاوزين أو المقتربين من الحد")
            risky_df = summary_df[summary_df["total_days"] >= SICK_LEAVE_ANNUAL_QUOTA * 0.7]
            if risky_df.empty:
                st.success("لا يوجد موظفون تجاوزوا أو اقتربوا من الحد السنوي حاليًا ✅")
            else:
                for _, r in risky_df.iterrows():
                    exceeded = r["total_days"] >= SICK_LEAVE_ANNUAL_QUOTA
                    with st.container(border=True):
                        e1, e2, e3 = st.columns([3, 2, 2])
                        with e1:
                            st.markdown(f"**{safe_str(r.get('name_ar'))}**")
                            st.caption(f"{fmt_id(r.get('employee_no'))} — {safe_str(r.get('department'))}")
                        with e2:
                            st.write(f"عدد الإجازات: {int(r.get('leave_count', 0))}")
                            st.write(f"إجمالي الأيام: {int(r.get('total_days', 0))}")
                        with e3:
                            if exceeded:
                                st.error(f"🔴 تجاوز الحد بـ {int(r.get('exceeded_days', 0))} يوم")
                            else:
                                st.warning(f"🟡 متبقي له {int(r.get('remaining_days', 0))} يوم فقط")

            st.markdown("### 📄 تصدير التقرير")
            sick_pdf_bytes = build_sick_leave_pdf(summary_df, year_label=period_label)
            sick_pdf_name = (
                f"sick_leave_report_"
                f"{sick_date_from.strftime('%Y%m%d')}_{sick_date_to.strftime('%Y%m%d')}.pdf"
            )

            st.download_button(
                label="📄 تصدير تقرير الإجازات المرضية PDF",
                data=sick_pdf_bytes,
                file_name=sick_pdf_name,
                mime="application/pdf",
                use_container_width=True,
                key="sick_leave_pdf_download_btn"
            )

    st.markdown("</div>", unsafe_allow_html=True)


def page_summary():
    st.markdown(
        '<div class="card"><div class="card-title">📋 ملخص الإجازات الشامل لكل الموظفين</div>',
        unsafe_allow_html=True
    )

    try:
        all_leaves_summary_src = store.load("leaves")

        if all_leaves_summary_src.empty or "leave_type" not in all_leaves_summary_src.columns:
            st.info("لا توجد بيانات إجازات بعد.")
        else:
            valid_dates = pd.to_datetime(all_leaves_summary_src.get("start_date"), errors="coerce").dropna()
            default_from = valid_dates.min().date() if not valid_dates.empty else dt.date(2020, 1, 1)
            default_to = dt.date.today()

            c1, c2 = st.columns(2)
            with c1:
                allsum_date_from = st.date_input(
                    "من تاريخ",
                    value=default_from,
                    key="allsum_leave_date_from"
                )
            with c2:
                allsum_date_to = st.date_input(
                    "إلى تاريخ",
                    value=default_to,
                    key="allsum_leave_date_to"
                )

            if allsum_date_to < allsum_date_from:
                st.error("تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية")
                allsum_summary_df = pd.DataFrame()
            else:
                allsum_summary_df = compute_all_leave_summary(
                    all_leaves_summary_src,
                    date_from=allsum_date_from,
                    date_to=allsum_date_to,
                )

            allsum_period_label = f"{fmt_date(allsum_date_from)} → {fmt_date(allsum_date_to)}"

            if allsum_summary_df.empty:
                st.info("لا توجد إجازات مسجلة ضمن الفترة المحددة.")
            else:
                total_employees = len(allsum_summary_df)
                total_leaves_all = int(allsum_summary_df["leave_count"].sum())
                total_days_all = int(allsum_summary_df["total_days"].sum())

                m1, m2, m3 = st.columns(3)
                m1.metric("👥 عدد الموظفين", total_employees)
                m2.metric("📄 إجمالي عدد الإجازات", total_leaves_all)
                m3.metric("📅 إجمالي أيام الإجازات", total_days_all)

                display_df = allsum_summary_df.copy()
                display_df["الترتيب"] = display_df["rank"]
                display_df["الموظف"] = display_df["name_ar"]
                display_df["الرقم الوظيفي"] = display_df["employee_no"].apply(fmt_id)
                display_df["القسم"] = display_df["department"]
                display_df["عدد الإجازات"] = display_df["leave_count"]
                display_df["إجمالي أيام الإجازات"] = display_df["total_days"]
                display_df["آخر إجازة"] = display_df["last_leave_date"].apply(fmt_date)
                display_df["نوع آخر إجازة"] = display_df["آخر_نوع_إجازة"].apply(safe_str)
                display_df["تفصيل الإجازات حسب النوع"] = display_df["نوع_الإجازات_تفصيلي"]

                table_df = display_df[[
                    "الترتيب",
                    "الموظف",
                    "الرقم الوظيفي",
                    "القسم",
                    "عدد الإجازات",
                    "إجمالي أيام الإجازات",
                    "آخر إجازة",
                    "نوع آخر إجازة",
                    "تفصيل الإجازات حسب النوع",
                ]].reset_index(drop=True)

                st.dataframe(
                    table_df,
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown("### 📄 تصدير التقرير")
                try:
                    allsum_pdf_bytes = build_all_leave_summary_pdf(allsum_summary_df, year_label=allsum_period_label)
                    allsum_pdf_name = (
                        f"all_leaves_summary_"
                        f"{allsum_date_from.strftime('%Y%m%d')}_{allsum_date_to.strftime('%Y%m%d')}.pdf"
                    )
                    st.download_button(
                        label="📄 تصدير ملخص الإجازات PDF",
                        data=allsum_pdf_bytes,
                        file_name=allsum_pdf_name,
                        mime="application/pdf",
                        use_container_width=True,
                        key="allsum_leave_pdf_download_btn"
                    )
                except Exception as pdf_err:
                    st.warning(f"⚠️ تعذّر إنشاء ملف PDF لهذا التقرير: {pdf_err}")
    except Exception as tab_err:
        st.error(f"⚠️ حدث خطأ أثناء عرض ملخص الإجازات: {tab_err}")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# التنقل الرئيسي
# =========================================================
PAGES = ["📊 تقرير البصمة", "🏖️ الإجازات", "⏰ الغياب والتأخير", "📑 التقارير"]
page = nav(PAGES, "main_nav")
st.markdown('<div class="subnav-gap"></div>', unsafe_allow_html=True)

if page == PAGES[0]:
    page_attendance()
elif page == PAGES[1]:
    records_page("leaves")
elif page == PAGES[2]:
    records_page("absences")
else:
    sub = nav(["👤 تقرير موظف", "🤒 الإجازات المرضية", "📋 ملخص الإجازات"], "reports_nav")
    if sub.startswith("👤"):
        page_emp_report()
    elif sub.startswith("🤒"):
        page_sick()
    else:
        page_summary()
