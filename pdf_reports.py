# =========================
# pdf_reports.py — كل تقارير PDF (تقرير البصمة، الإجازات، المرضية، الملخص)
# =========================
import os
import datetime as dt
from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from core import *  # noqa: F401,F403
from core import _PDF_EMOJI_PATTERN

PDF_NAVY = colors.HexColor("#1e293b")
PDF_NAVY_HEADER = colors.HexColor("#334155")
PDF_TEXT_GREY = colors.HexColor("#6b7280")
PDF_GRID_COLOR = colors.HexColor("#cbd5e1")
PDF_ROW_ALT = colors.HexColor("#f8fafc")


def pdf_page_decorator(font_name: str = "Helvetica", lang: str = "ar"):
    """
    دالة تذييل/شعار موحّدة تُستخدم في كل تقارير PDF بالتطبيق حتى تظهر كلها
    بنفس الشكل: شعار الشركة أعلى يمين كل صفحة (لو موجود)، وخط فاصل + رقم
    الصفحة + تاريخ ووقت إصدار التقرير أسفل كل صفحة.
    ملاحظة: رقم الصفحة يُكتب دايمًا بخط Helvetica بالإنجليزي في التقارير
    الإنجليزية، عشان الخط المستخدم فيها (Helvetica) مفيهوش حروف عربي أصلاً.
    """
    generated_at = dt.datetime.now().strftime("%d-%m-%Y %H:%M")
    is_ar = lang == "ar"

    def _decorate(canvas, doc):
        canvas.saveState()
        W, H = A4

        if os.path.exists(LOGO_PATH):
            try:
                img = ImageReader(LOGO_PATH)
                w, h = 2.6 * cm, 1.2 * cm
                x = W - doc.rightMargin - w
                y = H - doc.topMargin - h + 0.15 * cm
                canvas.drawImage(img, x, y, width=w, height=h, mask="auto")
            except Exception:
                pass

        canvas.setStrokeColor(PDF_GRID_COLOR)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 1.05 * cm, W - doc.rightMargin, 1.05 * cm)

        canvas.setFillColor(PDF_TEXT_GREY)
        page_no = canvas.getPageNumber()
        if is_ar:
            try:
                canvas.setFont(font_name, 8)
            except Exception:
                canvas.setFont("Helvetica", 8)
            canvas.drawRightString(W - doc.rightMargin, 0.65 * cm, ar(f"صفحة {page_no}"))
        else:
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(W - doc.rightMargin, 0.65 * cm, f"Page {page_no}")

        canvas.setFont("Helvetica", 8)
        canvas.drawString(doc.leftMargin, 0.65 * cm, f"Generated: {generated_at}")

        canvas.restoreState()

    return _decorate


def build_pdf(emp_row, late_emp: pd.DataFrame, abs_emp: pd.DataFrame, leave_emp: pd.DataFrame | None = None, lang: str = "ar", excuses_df: pd.DataFrame | None = None) -> bytes:
    FONT_EN = "Helvetica"
    FONT_AR_NAME = "AR"

    if not os.path.exists(FONT_PATH):
        raise FileNotFoundError(f"Arabic font not found: {FONT_PATH}")
    try:
        pdfmetrics.registerFont(TTFont(FONT_AR_NAME, FONT_PATH))
    except Exception:
        pass

    font_main = FONT_AR_NAME if lang == "ar" else FONT_EN

    align_text = 2 if lang == "ar" else 0
    align_head = 2 if lang == "ar" else 0

    def txt(x):
        s = safe_str(x)
        if lang == "ar":
            return ar(s)
        # الإصدار الإنجليزي يستخدم خط Helvetica اللي مفيهوش رموز إيموجي،
        # فبنشيلها هنا برضو عشان التقرير الإنجليزي يطلع نضيف زي العربي
        return _PDF_EMOJI_PATTERN.sub("", s).strip()

    def mixed_txt(x):
        """
        نص ممكن يكون عربي حتى داخل التقرير الإنجليزي (زي نوع الإجازة).
        بيترجع خلية Paragraph حقيقية بخط عربي عشان تتفسّر صح جوّه الجدول
        (خلية نصية عادية في reportlab بتتجاهل أي وسم/تنسيق داخلها).
        """
        s = safe_str(x)
        if not s:
            return ""
        return Paragraph(ar(s), ar_cell_style)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("title", parent=styles["Title"], fontName=font_main, fontSize=18, alignment=1)
    name_style = ParagraphStyle("name", parent=styles["BodyText"], fontName=font_main, fontSize=12, alignment=1, leading=16)

    info_font = font_main if lang == "ar" else FONT_EN
    info_style = ParagraphStyle(
        "info",
        parent=styles["BodyText"],
        fontName=info_font,
        fontSize=10,
        alignment=1,
        textColor=colors.grey,
        leading=14,
    )

    note_style = ParagraphStyle(
        "note",
        parent=styles["BodyText"],
        fontName=font_main if lang == "ar" else FONT_EN,
        fontSize=10,
        alignment=2 if lang == "ar" else 0,
        textColor=colors.HexColor("#8B5CF6"),
        leading=14,
        spaceBefore=6,
        spaceAfter=6,
    )

    h_style = ParagraphStyle("h", parent=title_style, fontName=font_main, fontSize=12, alignment=align_head, spaceAfter=6)
    p_style = ParagraphStyle("p", parent=styles["BodyText"], fontName=font_main, fontSize=10.5, alignment=align_text, leading=15)
    total_style = ParagraphStyle("total", parent=p_style, fontName=font_main, fontSize=12.0, alignment=align_text, leading=18)
    # نوع الإجازة نص عربي دايمًا حتى لو التقرير بالإنجليزي، فبنعرضه بخط عربي مخصص
    # جوّه Paragraph حقيقي (مش نص عادي) عشان أي وسم HTML/خط نستخدمه يتفسّر صح.
    ar_cell_style = ParagraphStyle(
        "ar_cell", parent=styles["BodyText"], fontName=FONT_AR_NAME,
        fontSize=9.5, alignment=2, leading=13,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )

    name_ar_ = safe_str(emp_row.get("name_ar", ""))
    name_en_ = safe_str(emp_row.get("name_en", ""))
    nat = safe_str(emp_row.get("nationality", emp_row.get("nationality_raw", "")))
    emp_no = fmt_id(emp_row.get("employee_no", ""))
    dept = safe_str(emp_row.get("department", ""))
    job = safe_str(emp_row.get("job_title", ""))

    title = month_year_title(emp_row) if lang == "ar" else month_year_title_en(emp_row)
    attendance_rule = safe_str(emp_row.get("attendance_calculation", "")).strip().lower()

    if lang == "ar":
        info_parts = []
        if emp_no:
            info_parts.append(f"الكود/الرقم: {emp_no}")
        if job:
            info_parts.append(f"الوظيفة: {job}")
        if dept:
            info_parts.append(f"الإدارة: {dept}")
        if nat:
            info_parts.append(f"الجنسية: {nat}")
        info_line = ar(" | ".join(info_parts))
    else:
        parts = []
        if emp_no:
            parts.append(escape(f"Employee No: {emp_no}"))
        if job:
            parts.append(f"Job Title: <font name='AR'>{ar(job)}</font>" if AR_CHARS.search(job) else escape(f"Job Title: {job}"))
        if dept:
            parts.append(f"Department: <font name='AR'>{ar(dept)}</font>" if AR_CHARS.search(dept) else escape(f"Department: {dept}"))
        if nat:
            parts.append(f"Nationality: <font name='AR'>{ar(nat)}</font>" if AR_CHARS.search(nat) else escape(f"Nationality: {nat}"))
        info_line = " | ".join(parts)

    page_decorator = pdf_page_decorator(font_main, lang)

    def fmt_time(x):
        try:
            tt = pd.to_datetime(str(x), errors="coerce")
            return "" if pd.isna(tt) else tt.strftime("%H:%M")
        except Exception:
            return ""

    def rtl_row(row):
        return list(reversed(row)) if lang == "ar" else row

    def rtl_cols(widths):
        return list(reversed(widths)) if lang == "ar" else widths

    if lang == "ar":
        name_line = f"{name_ar_} — {name_en_}" if name_en_ else name_ar_
        name_paragraph = Paragraph(ar(name_line), name_style)
    else:
        en_part = escape(name_en_ or "")
        ar_part = ar(name_ar_) if name_ar_ else ""
        if en_part and ar_part:
            mixed = f"{en_part} — <font name='AR'>{ar_part}</font>"
        elif en_part:
            mixed = en_part
        else:
            mixed = f"<font name='AR'>{ar_part}</font>"
        name_paragraph = Paragraph(mixed, name_style)

    story = []
    story.append(Paragraph(txt(title), title_style))
    story.append(name_paragraph)
    story.append(Paragraph(info_line, info_style))
    story.append(Spacer(1, 6))

    if attendance_rule == "daily_hours":
        if lang == "ar":
            note = "📝 ملاحظة: يتم احتساب التأخير بعد بداية الدوام مع السماح، والخروج المبكر قبل نهاية الدوام، والإضافي بعد نهاية الدوام."
            story.append(Paragraph(ar(note), note_style))
        else:
            note = "📝 Note: Late is calculated after shift start with grace, early leave before shift end, and overtime after shift end."
            story.append(Paragraph(txt(note), note_style))
    else:
        if lang == "ar":
            note = "📝 ملاحظة: يتم احتساب التأخير بعد بداية الدوام مع السماح، والخروج المبكر قبل نهاية الدوام المحددة."
            story.append(Paragraph(ar(note), note_style))
        else:
            note = "📝 Note: Late is calculated after shift start with grace, and early leave before official shift end."
            story.append(Paragraph(txt(note), note_style))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.lightgrey))
    story.append(Spacer(1, 8))

    section_title = "التأخير والخروج المبكر والإضافي" if lang == "ar" else "Late / Early Leave / Overtime"
    story.append(Paragraph(txt(section_title), h_style))

    if late_emp is None or late_emp.empty:
        story.append(Paragraph(txt(t("لا يوجد بيانات", "No records", lang)), p_style))
    else:
        le = late_emp.copy()
        if "date" in le.columns:
            le = le.sort_values("date")
            le["date"] = le["date"].apply(fmt_date)

        if "worked_minutes" not in le.columns:
            le["worked_minutes"] = 0
        if "overtime_minutes" not in le.columns:
            le["overtime_minutes"] = 0
        if "early_leave_minutes" not in le.columns:
            le["early_leave_minutes"] = 0

        if attendance_rule == "daily_hours":
            rows = [rtl_row([
                txt(t("اليوم", "Day", lang)),
                txt(t("التاريخ", "Date", lang)),
                txt(t("أول بصمة", "First In", lang)),
                txt(t("آخر بصمة", "Last Out", lang)),
                txt(t("ساعات العمل", "Worked", lang)),
                txt(t("التأخير", "Late", lang)),
                txt(t("الخروج المبكر", "Early Leave", lang)),
                txt(t("الإضافي", "Overtime", lang)),
            ])]

            for _, r in le.iterrows():
                day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
                row = [
                    txt(day_val),
                    txt(safe_str(r.get("date", ""))),
                    txt(fmt_time(r.get("first_punch_time", ""))),
                    txt(fmt_time(r.get("last_punch_time", ""))),
                    txt(mm_to_hhmm(int(r.get("worked_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("late_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("early_leave_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("overtime_minutes", 0) or 0))),
                ]
                rows.append(rtl_row(row))

            widths = rtl_cols([2.2*cm, 2.7*cm, 2.2*cm, 2.2*cm, 2.6*cm, 2.2*cm, 2.6*cm, 2.2*cm])
            t1 = Table(rows, colWidths=widths)
        else:
            rows = [rtl_row([
                txt(t("اليوم", "Day", lang)),
                txt(t("التاريخ", "Date", lang)),
                txt(t("أول بصمة", "First Punch", lang)),
                txt(t("آخر بصمة", "Last Punch", lang)),
                txt(t("التأخير", "Late", lang)),
                txt(t("الخروج المبكر", "Early Leave", lang)),
            ])]

            for _, r in le.iterrows():
                day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
                row = [
                    txt(day_val),
                    txt(safe_str(r.get("date", ""))),
                    txt(fmt_time(r.get("first_punch_time", ""))),
                    txt(fmt_time(r.get("last_punch_time", ""))),
                    txt(mm_to_hhmm(int(r.get("late_minutes", 0) or 0))),
                    txt(mm_to_hhmm(int(r.get("early_leave_minutes", 0) or 0))),
                ]
                rows.append(rtl_row(row))

            widths = rtl_cols([3.0*cm, 3.2*cm, 2.8*cm, 2.8*cm, 2.8*cm, 3.0*cm])
            t1 = Table(rows, colWidths=widths)

        t1.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_main),
            ("FONTSIZE", (0, 0), (-1, 0), 10.0),
            ("FONTSIZE", (0, 1), (-1, -1), 9.2),
            ("BACKGROUND", (0, 0), (-1, 0), PDF_NAVY_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t1)
        story.append(Spacer(1, 8))

        total_late = int(emp_row.get("total_late_minutes", 0) or 0)
        total_early_leave = int(emp_row.get("total_early_leave_minutes", 0) or 0)
        total_overtime = int(emp_row.get("total_overtime_minutes", 0) or 0)
        total_deduction = total_late + total_early_leave

        if lang == "ar":
            story.append(Paragraph(ar(f"⏱ إجمالي التأخير: {mm_to_ar_hm(total_late)}"), total_style))
            story.append(Paragraph(ar(f"🚪 إجمالي الخروج المبكر: {mm_to_ar_hm(total_early_leave)}"), total_style))

            if attendance_rule == "daily_hours":
                story.append(Paragraph(ar(f"⬆️ إجمالي الإضافي: {mm_to_ar_hm(total_overtime)}"), total_style))
                net_minutes = total_overtime - total_deduction
                if net_minutes > 0:
                    net_line = f"✅ الصافي النهائي: إضافي {mm_to_ar_hm(net_minutes)}"
                elif net_minutes < 0:
                    net_line = f"❌ الصافي النهائي: عجز {mm_to_ar_hm(net_minutes)}"
                else:
                    net_line = "➖ الصافي النهائي: متعادل (0 دقيقة)"
                story.append(Paragraph(ar(net_line), total_style))
            else:
                story.append(Paragraph(ar(f"📌 إجمالي التأخير + الخروج المبكر: {mm_to_ar_hm(total_deduction)}"), total_style))
        else:
            story.append(Paragraph(f"Total Late: {mm_to_hhmm(total_late)}", total_style))
            story.append(Paragraph(f"Total Early Leave: {mm_to_hhmm(total_early_leave)}", total_style))
            if attendance_rule == "daily_hours":
                story.append(Paragraph(f"Total Overtime: {mm_to_hhmm(total_overtime)}", total_style))
                net_minutes = total_overtime - total_deduction
                if net_minutes > 0:
                    net_line = f"Final Net: Overtime {mm_to_hhmm(net_minutes)}"
                elif net_minutes < 0:
                    net_line = f"Final Net: Deficit {mm_to_hhmm(net_minutes)}"
                else:
                    net_line = "Final Net: Balanced (0m)"
                story.append(Paragraph(net_line, total_style))
            else:
                story.append(Paragraph(f"Total Late + Early Leave: {mm_to_hhmm(total_deduction)}", total_style))

    story.append(Spacer(1, 12))

    story.append(Paragraph(txt(t("الغياب", "Absence", lang)), h_style))
    if abs_emp is None or abs_emp.empty:
        story.append(Paragraph(txt(t("لا يوجد غياب", "No absence records", lang)), p_style))
    else:
        ae = abs_emp.copy().sort_values("date") if "date" in abs_emp.columns else abs_emp.copy()
        if "date" in ae.columns:
            ae["date"] = ae["date"].apply(fmt_date)

        has_type = "absence_type" in ae.columns

        header2 = [txt(t("اليوم", "Day", lang)), txt(t("التاريخ", "Date", lang))]
        if has_type:
            header2 += [txt(t("نوع الغياب", "Absence Type", lang)), txt(t("السبب", "Reason", lang))]
        rows2 = [rtl_row(header2)]

        for _, r in ae.iterrows():
            day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
            row = [txt(day_val), txt(safe_str(r.get("date", "")))]
            if has_type:
                row += [mixed_txt(r.get("absence_type")), mixed_txt(safe_str(r.get("absence_reason")) or "—")]
            rows2.append(rtl_row(row))

        abs_widths = [3.0 * cm, 3.2 * cm, 4.8 * cm, 7.5 * cm] if has_type else [6.0 * cm, 9.5 * cm]
        t2 = Table(rows2, colWidths=rtl_cols(abs_widths))
        t2.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_main),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), PDF_NAVY_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t2)
        story.append(Spacer(1, 6))

        absent_days = int(emp_row.get("absent_days", 0) or 0)
        story.append(Paragraph(txt(t(f"🚫 عدد أيام الغياب: {absent_days}", f"🚫 Total Absent Days: {absent_days}", lang)), total_style))
        if has_type:
            excused_n = int((ae["absence_type"] == "غياب بإذن").sum())
            unexcused_n = len(ae) - excused_n
            story.append(Paragraph(txt(t(
                f"منها بإذن: {excused_n}  |  بدون إذن: {unexcused_n}",
                f"Excused: {excused_n}  |  Unexcused: {unexcused_n}",
                lang,
            )), total_style))

    # الأعذار المسجلة للتأخير / الخروج المبكر / أخرى
    if excuses_df is not None and not excuses_df.empty:
        ex = excuses_df[excuses_df["record_type"].apply(safe_str).isin(LATE_TYPES | {"أخرى"})].copy()
        if not ex.empty:
            story.append(Spacer(1, 12))
            story.append(Paragraph(txt(t("أعذار التأخير والخروج المبكر", "Late / Early Leave Excuses", lang)), h_style))
            rows_ex = [rtl_row([
                txt(t("من", "From", lang)),
                txt(t("إلى", "To", lang)),
                txt(t("النوع", "Type", lang)),
                txt(t("السبب", "Reason", lang)),
            ])]
            for _, r in ex.iterrows():
                rows_ex.append(rtl_row([
                    txt(fmt_date(r.get("start_date"))),
                    txt(fmt_date(r.get("end_date"))),
                    mixed_txt(r.get("record_type")),
                    mixed_txt(safe_str(r.get("reason")) or "—"),
                ]))
            t_ex = Table(rows_ex, colWidths=rtl_cols([3.0 * cm, 3.0 * cm, 4.0 * cm, 8.5 * cm]))
            t_ex.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font_main),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, 0), PDF_NAVY_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t_ex)

    story.append(Spacer(1, 12))
    story.append(Paragraph(txt(t("الإجازات المعتمدة", "Approved Leaves", lang)), h_style))
    if leave_emp is None or leave_emp.empty:
        story.append(Paragraph(txt(t("لا توجد إجازات معتمدة", "No approved leaves", lang)), p_style))
    else:
        lv = leave_emp.copy().sort_values("date") if "date" in leave_emp.columns else leave_emp.copy()
        if "date" in lv.columns:
            lv["date"] = lv["date"].apply(fmt_date)
        rows3 = [rtl_row([
            txt(t("اليوم", "Day", lang)),
            txt(t("التاريخ", "Date", lang)),
            txt(t("نوع الإجازة", "Leave Type", lang)),
        ])]
        for _, r in lv.iterrows():
            day_val = safe_str(r.get("weekday_ar", r.get("weekday", ""))) if lang == "ar" else safe_str(r.get("weekday", ""))
            rows3.append(rtl_row([
                txt(day_val),
                txt(safe_str(r.get("date", ""))),
                mixed_txt(safe_str(r.get("leave_type", "إجازة")) or "إجازة"),
            ]))
        t3 = Table(rows3, colWidths=rtl_cols([4.5 * cm, 4.5 * cm, 6.5 * cm]))
        t3.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_main),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), PDF_NAVY_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT" if lang == "ar" else "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t3)
        story.append(Spacer(1, 6))
        leave_days = int(emp_row.get("approved_leave_days", len(lv)) or 0)
        story.append(Paragraph(txt(t(f"🏖️ عدد أيام الإجازات المعتمدة: {leave_days}", f"🏖️ Total Approved Leave Days: {leave_days}", lang)), total_style))

    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
    return buf.getvalue()


def build_leaves_pdf(leaves_df: pd.DataFrame) -> bytes:

    buf = BytesIO()

    FONT_NAME = "AR_LEAVE"

    try:
        pdfmetrics.registerFont(
            TTFont(FONT_NAME, FONT_PATH)
        )
    except Exception:
        pass

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.7 * cm,
        rightMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
    )

    styles = getSampleStyleSheet()

    # =====================================================
    # STYLES
    # =====================================================

    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=18,
        alignment=1,
        textColor=colors.HexColor("#111827"),
        leading=24,
        spaceAfter=18,
    )

    employee_style = ParagraphStyle(
        "employee_style",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        alignment=2,
        leading=18,
        textColor=colors.white,
    )

    header_style = ParagraphStyle(
        "header_style",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10,
        alignment=1,
        textColor=colors.white,
        leading=14,
    )

    cell_style = ParagraphStyle(
        "cell_style",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9,
        alignment=1,
        textColor=colors.black,
        leading=13,
    )

    notes_style = ParagraphStyle(
        "notes_style",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=8.5,
        alignment=2,
        textColor=colors.black,
        leading=11,
    )

    total_style = ParagraphStyle(
        "total_style",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        alignment=2,
        textColor=colors.HexColor("#111827"),
        leading=16,
        spaceBefore=12,
    )

    def rtl_row(row):
        return list(reversed(row))

    # =====================================================
    # بداية التقرير
    # =====================================================

    story = []

    story.append(
        Paragraph(
            ar("تقرير الإجازات"),
            title_style
        )
    )

    # =====================================================
    # لا توجد بيانات
    # =====================================================

    if leaves_df is None or leaves_df.empty:

        story.append(
            Paragraph(
                ar("لا توجد بيانات"),
                cell_style
            )
        )

        page_decorator = pdf_page_decorator(FONT_NAME)
        doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)

        return buf.getvalue()

    # =====================================================
    # تجهيز البيانات
    # =====================================================

    pdf_df = leaves_df.copy()

    pdf_df["start_date"] = pd.to_datetime(
        pdf_df["start_date"],
        errors="coerce"
    )

    pdf_df["end_date"] = pd.to_datetime(
        pdf_df["end_date"],
        errors="coerce"
    )

    # 🔥 توحيد الرقم الوظيفي قبل التجميع، ونجمع حسب الرقم الوظيفي فقط (مش
    # الاسم). ده عشان لو نفس الموظف اتسجل اسمه بصيغتين مختلفتين شوية (زي
    # "محمد أحمد الحميد" و"محمد احمد الحميد" - فرق همزة بسيط) ما يتقسمش
    # كأنه موظفين مختلفين في التقرير، طول ما رقمه الوظيفي واحد.
    pdf_df["employee_id"] = pdf_df["employee_id"].apply(fmt_id)
    pdf_df["employee_no"] = pdf_df["employee_no"].apply(fmt_id)

    grouped = pdf_df.groupby(
        ["employee_id", "employee_no"],
        dropna=False
    )

    total_records = 0
    total_leave_days = 0

    # =====================================================
    # الموظفين
    # =====================================================

    for (
        employee_id,
        employee_no
    ), emp_df in grouped:

        # الاسم المعروض: أول اسم غير فاضي مسجل لنفس الرقم الوظيفي
        employee_name = ""
        for _nm in emp_df["name_ar"]:
            _nm = safe_str(_nm)
            if _nm:
                employee_name = _nm
                break
        employee_no = fmt_id(employee_no)

        leave_count = len(emp_df)

        employee_total_days = 0

        # =================================================
        # حساب إجمالي الأيام
        # =================================================

        for _, rr in emp_df.iterrows():

            s = pd.to_datetime(
                rr.get("start_date"),
                errors="coerce"
            )

            e = pd.to_datetime(
                rr.get("end_date"),
                errors="coerce"
            )

            if pd.notna(s) and pd.notna(e):

                employee_total_days += (
                    (e - s).days + 1
                )

        total_records += leave_count
        total_leave_days += employee_total_days

        # =================================================
        # عنوان الموظف
        # =================================================

        employee_header = Table(
            [[
                Paragraph(
                    ar(
                        f"{employee_name}"
                        f"    |    الرقم الوظيفي: {employee_no}"
                        f"    |    عدد الإجازات: {leave_count}"
                        f"    |    إجمالي الأيام: {employee_total_days}"
                    ),
                    employee_style
                )
            ]],
            colWidths=[18.8 * cm]
        )

        employee_header.setStyle(TableStyle([

            ("BACKGROUND",
             (0, 0),
             (-1, -1),
             colors.HexColor("#1e293b")),

            ("BOX",
             (0, 0),
             (-1, -1),
             0.5,
             colors.HexColor("#0f172a")),

            ("BOTTOMPADDING",
             (0, 0),
             (-1, -1),
             8),

            ("TOPPADDING",
             (0, 0),
             (-1, -1),
             8),

            ("RIGHTPADDING",
             (0, 0),
             (-1, -1),
             10),

        ]))

        story.append(employee_header)

        story.append(
            Spacer(1, 0.15 * cm)
        )

        # =================================================
        # جدول التفاصيل
        # =================================================

        rows = [
            rtl_row([

                Paragraph(
                    ar("نوع الإجازة"),
                    header_style
                ),

                Paragraph(
                    ar("من"),
                    header_style
                ),

                Paragraph(
                    ar("إلى"),
                    header_style
                ),

                Paragraph(
                    ar("عدد الأيام"),
                    header_style
                ),

                Paragraph(
                    ar("ملاحظات"),
                    header_style
                ),

            ])
        ]

        # =================================================
        # تفاصيل الإجازات
        # =================================================

        for _, r in emp_df.iterrows():

            leave_type = safe_str(
                r.get("leave_type", "")
            ) or "—"

            start_date = fmt_date(
                r.get("start_date")
            )

            end_date = fmt_date(
                r.get("end_date")
            )

            notes_text = safe_str(
                r.get("notes", "")
            ) or "—"

            s = pd.to_datetime(
                r.get("start_date"),
                errors="coerce"
            )

            e = pd.to_datetime(
                r.get("end_date"),
                errors="coerce"
            )

            days_count = 1

            if pd.notna(s) and pd.notna(e):

                days_count = (
                    (e - s).days + 1
                )

            rows.append(
                rtl_row([

                    Paragraph(
                        ar(leave_type),
                        cell_style
                    ),

                    Paragraph(
                        ar(start_date),
                        cell_style
                    ),

                    Paragraph(
                        ar(end_date),
                        cell_style
                    ),

                    Paragraph(
                        ar(str(days_count)),
                        cell_style
                    ),

                    Paragraph(
                        ar(notes_text),
                        notes_style
                    ),

                ])
            )

        # =================================================
        # إنشاء الجدول
        # =================================================

        details_table = Table(
            rows,
            colWidths=[
                2.0 * cm,
                4.0 * cm,
                4.0 * cm,
                4.0 * cm,
                5.8 * cm,
            ],
            repeatRows=1,
        )

        details_table.setStyle(TableStyle([

            # HEADER
            ("BACKGROUND",
             (0, 0),
             (-1, 0),
             colors.HexColor("#334155")),

            ("TEXTCOLOR",
             (0, 0),
             (-1, 0),
             colors.white),

            ("FONTNAME",
             (0, 0),
             (-1, -1),
             FONT_NAME),

            ("GRID",
             (0, 0),
             (-1, -1),
             0.4,
             colors.HexColor("#cbd5e1")),

            ("ALIGN",
             (0, 0),
             (-1, -1),
             "CENTER"),

            ("VALIGN",
             (0, 0),
             (-1, -1),
             "MIDDLE"),

            ("BOTTOMPADDING",
             (0, 0),
             (-1, -1),
             6),

            ("TOPPADDING",
             (0, 0),
             (-1, -1),
             6),

            # ROW COLORS
            ("ROWBACKGROUNDS",
             (0, 1),
             (-1, -1),
             [
                 colors.white,
                 colors.HexColor("#f8fafc")
             ]),

        ]))

        story.append(details_table)

        story.append(
            Spacer(1, 0.5 * cm)
        )

    # =====================================================
    # الإجماليات (إجمالي السجلات + إجمالي الأيام + تفصيل حسب النوع)
    # =====================================================

    type_days = {}
    for _, rr in pdf_df.iterrows():
        lt = safe_str(rr.get("leave_type")) or "غير محدد"
        s = pd.to_datetime(rr.get("start_date"), errors="coerce")
        e = pd.to_datetime(rr.get("end_date"), errors="coerce")
        d = (e - s).days + 1 if pd.notna(s) and pd.notna(e) else 0
        type_days[lt] = type_days.get(lt, 0) + d

    breakdown_line = "   |   ".join(
        f"{k}: {v} يوم" for k, v in sorted(type_days.items(), key=lambda x: -x[1])
    )

    summary_lines = [
        ar(
            f"👥 عدد الموظفين: {grouped.ngroups}    |    "
            f"📄 إجمالي سجلات الإجازات: {total_records}    |    "
            f"📅 إجمالي أيام الإجازات: {total_leave_days}"
        )
    ]
    if breakdown_line:
        summary_lines.append(ar(f"تفصيل حسب نوع الإجازة: {breakdown_line}"))

    summary_table = Table(
        [[Paragraph("<br/>".join(summary_lines), total_style)]],
        colWidths=[18.8 * cm]
    )

    summary_table.setStyle(TableStyle([

        ("BACKGROUND",
         (0, 0),
         (-1, -1),
         colors.HexColor("#e2e8f0")),

        ("BOX",
         (0, 0),
         (-1, -1),
         0.5,
         colors.HexColor("#94a3b8")),

        ("BOTTOMPADDING",
         (0, 0),
         (-1, -1),
         8),

        ("TOPPADDING",
         (0, 0),
         (-1, -1),
         8),

    ]))

    story.append(summary_table)

    # =====================================================
    # BUILD PDF
    # =====================================================

    page_decorator = pdf_page_decorator(FONT_NAME)
    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)

    return buf.getvalue()



def build_sick_leave_pdf(summary_df: pd.DataFrame, year_label: str = "") -> bytes:
    """
    تقرير PDF لملخص الإجازات المرضية لكل موظف مرتب من الأكثر إلى الأقل،
    مع تمييز الموظفين المتجاوزين للحد السنوي (30 يوم).
    """
    buf = BytesIO()

    FONT_NAME = "AR_SICK"
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
    except Exception:
        pass

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.7 * cm,
        rightMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "sick_title",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=18,
        alignment=1,
        textColor=colors.HexColor("#111827"),
        leading=24,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "sick_subtitle",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        alignment=1,
        textColor=colors.HexColor("#374151"),
        leading=16,
        spaceAfter=14,
    )

    header_style = ParagraphStyle(
        "sick_header",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10,
        alignment=1,
        textColor=colors.white,
        leading=14,
    )

    cell_style = ParagraphStyle(
        "sick_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9.5,
        alignment=1,
        textColor=colors.black,
        leading=13,
    )

    total_style = ParagraphStyle(
        "sick_total",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        alignment=2,
        textColor=colors.HexColor("#111827"),
        leading=16,
        spaceBefore=12,
    )

    def rtl_row(row):
        return list(reversed(row))

    story = []
    story.append(Paragraph(ar("تقرير الإجازات المرضية حسب الموظف"), title_style))
    if year_label:
        story.append(Paragraph(ar(f"الفترة: {year_label}"), subtitle_style))
    story.append(
        Paragraph(
            ar(f"الحد السنوي المسموح به لكل موظف: {SICK_LEAVE_ANNUAL_QUOTA} يوم"),
            subtitle_style,
        )
    )

    if summary_df is None or summary_df.empty:
        story.append(Paragraph(ar("لا توجد إجازات مرضية ضمن الفترة المحددة"), cell_style))
        page_decorator = pdf_page_decorator(FONT_NAME)
        doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
        return buf.getvalue()

    # رأس الجدول (بالترتيب من اليمين لليسار بعد rtl_row)
    header_row = [
        Paragraph(ar("الحالة"), header_style),
        Paragraph(ar("المتبقي"), header_style),
        Paragraph(ar("إجمالي الأيام"), header_style),
        Paragraph(ar("عدد الإجازات"), header_style),
        Paragraph(ar("القسم"), header_style),
        Paragraph(ar("الرقم الوظيفي"), header_style),
        Paragraph(ar("الموظف"), header_style),
        Paragraph(ar("م"), header_style),
    ]

    rows = [header_row]
    row_colors = [colors.HexColor("#1e293b")]

    for _, r in summary_df.iterrows():
        exceeded = int(r.get("total_days", 0)) >= SICK_LEAVE_ANNUAL_QUOTA
        near_limit = int(r.get("total_days", 0)) >= SICK_LEAVE_ANNUAL_QUOTA * 0.7 and not exceeded

        row = [
            Paragraph(ar(safe_str(r.get("status"))), cell_style),
            Paragraph(ar(str(int(r.get("remaining_days", 0)))), cell_style),
            Paragraph(ar(str(int(r.get("total_days", 0)))), cell_style),
            Paragraph(ar(str(int(r.get("leave_count", 0)))), cell_style),
            Paragraph(ar(safe_str(r.get("department"))), cell_style),
            Paragraph(ar(fmt_id(r.get("employee_no"))), cell_style),
            Paragraph(ar(safe_str(r.get("name_ar"))), cell_style),
            Paragraph(ar(str(int(r.get("rank", 0)))), cell_style),
        ]
        rows.append(row)

        if exceeded:
            row_colors.append(colors.HexColor("#fee2e2"))
        elif near_limit:
            row_colors.append(colors.HexColor("#fef9c3"))
        else:
            row_colors.append(colors.white if len(row_colors) % 2 == 0 else colors.HexColor("#f8fafc"))

    col_widths = [1.6 * cm, 1.8 * cm, 2.3 * cm, 2.3 * cm, 3.2 * cm, 2.8 * cm, 5.0 * cm, 1.0 * cm]

    table = Table(rows, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, c in enumerate(row_colors):
        if i == 0:
            continue
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), c))

    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    exceeded_count = int((summary_df["total_days"] >= SICK_LEAVE_ANNUAL_QUOTA).sum())
    total_employees = len(summary_df)
    total_days_all = int(summary_df["total_days"].sum())

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            ar(f"👥 عدد الموظفين: {total_employees}    |    📅 إجمالي أيام الإجازات المرضية: {total_days_all}"),
            total_style,
        )
    )
    story.append(
        Paragraph(
            ar(f"🔴 عدد الموظفين المتجاوزين للحد السنوي ({SICK_LEAVE_ANNUAL_QUOTA} يوم): {exceeded_count}"),
            total_style,
        )
    )

    page_decorator = pdf_page_decorator(FONT_NAME)
    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
    return buf.getvalue()


def build_all_leave_summary_pdf(summary_df: pd.DataFrame, year_label: str = "") -> bytes:
    """
    تقرير PDF شامل لملخص إجازات كل الموظفين (كل الأنواع)،
    يعرض عدد الإجازات وإجمالي الأيام وآخر إجازة لكل موظف.
    """
    buf = BytesIO()

    FONT_NAME = "AR_ALLSUM"
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
    except Exception:
        pass

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0.7 * cm,
        rightMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "allsum_title",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=18,
        alignment=1,
        textColor=colors.HexColor("#111827"),
        leading=24,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "allsum_subtitle",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        alignment=1,
        textColor=colors.HexColor("#374151"),
        leading=16,
        spaceAfter=14,
    )

    header_style = ParagraphStyle(
        "allsum_header",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10,
        alignment=1,
        textColor=colors.white,
        leading=14,
    )

    cell_style = ParagraphStyle(
        "allsum_cell",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9.5,
        alignment=1,
        textColor=colors.black,
        leading=13,
    )

    total_style = ParagraphStyle(
        "allsum_total",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        alignment=2,
        textColor=colors.HexColor("#111827"),
        leading=16,
        spaceBefore=12,
    )

    story = []
    story.append(Paragraph(ar("ملخص الإجازات الشامل لكل الموظفين"), title_style))
    if year_label:
        story.append(Paragraph(ar(f"الفترة: {year_label}"), subtitle_style))

    if summary_df is None or summary_df.empty:
        story.append(Paragraph(ar("لا توجد إجازات مسجلة ضمن الفترة المحددة"), cell_style))
        page_decorator = pdf_page_decorator(FONT_NAME)
        doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
        return buf.getvalue()

    # رأس الجدول (بالترتيب من اليمين لليسار بعد rtl_row)
    header_row = [
        Paragraph(ar("آخر إجازة"), header_style),
        Paragraph(ar("إجمالي الأيام"), header_style),
        Paragraph(ar("عدد الإجازات"), header_style),
        Paragraph(ar("القسم"), header_style),
        Paragraph(ar("الرقم الوظيفي"), header_style),
        Paragraph(ar("الموظف"), header_style),
        Paragraph(ar("م"), header_style),
    ]

    rows = [header_row]

    for _, r in summary_df.iterrows():
        row = [
            Paragraph(ar(fmt_date(r.get("last_leave_date"))), cell_style),
            Paragraph(ar(str(int(r.get("total_days", 0)))), cell_style),
            Paragraph(ar(str(int(r.get("leave_count", 0)))), cell_style),
            Paragraph(ar(safe_str(r.get("department"))), cell_style),
            Paragraph(ar(fmt_id(r.get("employee_no"))), cell_style),
            Paragraph(ar(safe_str(r.get("name_ar"))), cell_style),
            Paragraph(ar(str(int(r.get("rank", 0)))), cell_style),
        ]
        rows.append(row)

    col_widths = [2.4 * cm, 2.3 * cm, 2.3 * cm, 3.4 * cm, 2.8 * cm, 5.3 * cm, 1.0 * cm]

    table = Table(rows, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(rows)):
        style_cmds.append((
            "BACKGROUND", (0, i), (-1, i),
            colors.white if i % 2 == 0 else colors.HexColor("#f8fafc"),
        ))

    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    total_employees = len(summary_df)
    total_days_all = int(summary_df["total_days"].sum())
    total_leaves_all = int(summary_df["leave_count"].sum())

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            ar(
                f"👥 عدد الموظفين: {total_employees}    |    "
                f"📄 إجمالي عدد الإجازات: {total_leaves_all}    |    "
                f"📅 إجمالي أيام الإجازات: {total_days_all}"
            ),
            total_style,
        )
    )

    page_decorator = pdf_page_decorator(FONT_NAME)
    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
    return buf.getvalue()
