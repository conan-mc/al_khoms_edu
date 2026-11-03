# -*- coding: utf-8 -*-
"""
print_helpers.py — مولّدات بيانات قوالب الطباعة الرسمية الأربعة.

الدوال العامة (تُسجَّل في Jinja عبر hooks.py → jinja.methods):
    card_context(student, program=None)          بطاقة الطالب الدراسية
    transcript_context(student, program=None)    كشف الدرجات
    notice_context(ssr_name)                     إشعار النتيجة الفصلي
    final_result_context(student, program=None)  نموذج النتيجة

كلها قراءة-فقط، وتُبنى الأرقام من سجلات Student Semester Result المخزنة
(المحتسبة بالمحرك الرسمي)، مع احتساب احتياطي بمحرك academic_rules نفسه عند
غياب سجل SSR لذلك الفصل.
"""

import frappe

from al_khoms_edu import academic_rules as rules


def _settings():
    """يجلب إعدادات القواعد الدراسية (مع fallback)."""
    return rules.get_rules()


# ---------------------------------------------------------------------------
# أدوات عامة
# ---------------------------------------------------------------------------

def fmt(value, precision=2):
    """تنسيق رقمي للعرض: 22.0 → «22» | 72.95 → «72.95»."""
    if value in (None, ""):
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if abs(num - round(num)) > 0.0001:
        return f"{num:.{precision}f}"
    return str(int(round(num)))


def _fmt_date(value):
    return frappe.utils.formatdate(value, "dd/MM/yyyy") if value else ""


def _clean_department(dept):
    return (dept or "").replace(" - AKI", "").strip()


def _split_term(term):
    """«2026/2025 (ربيع 2025)» → («2026/2025»، «ربيع»، «2025»)."""
    term = term or ""
    ay, season, year = term, "", ""
    if "(" in term and term.endswith(")"):
        ay, inner = term.split("(", 1)
        ay = ay.strip()
        parts = inner.rstrip(")").strip().split()
        if parts:
            season = parts[0]
            year = parts[1] if len(parts) > 1 else ""
    return ay, season, year


def _course_map():
    return {
        r.name: r
        for r in frappe.get_all("Course", fields=["name", "course_name", "course_code", "units"])
    }


def _resolve_program(student, program=None):
    """البرنامج المطلوب: الممرَّر، وإلا الأكثر وروداً في نتائج الطالب، وإلا تسجيلاته."""
    if program:
        return program
    rows = frappe.db.sql(
        """SELECT program, COUNT(*) AS c FROM `tabAssessment Result`
           WHERE student=%s AND docstatus=1
             AND program IS NOT NULL AND program != ''
           GROUP BY program ORDER BY c DESC LIMIT 1""",
        student,
        as_dict=True,
    )
    if rows:
        return rows[0].program
    pe = frappe.get_all(
        "Program Enrollment", filters={"student": student}, pluck="program", limit=1
    )
    return pe[0] if pe else None


def student_info(student, program=None):
    """بيانات الطالب للترويسة: الاسم، الأرقام، الميلاد، القسم، التخصص..."""
    program = _resolve_program(student, program)
    s = frappe.db.get_value(
        "Student",
        student,
        [
            "student_name",
            "legacy_student_number",
            "national_id",
            "date_of_birth",
            "birth_place_ak",
            "image",
            "graduation_date_ak",
        ],
        as_dict=True,
    ) or frappe._dict()
    dept = ""
    if program:
        dept = _clean_department(frappe.db.get_value("Program", program, "department"))
    enrollment = frappe.get_all(
        "Program Enrollment",
        filters={"student": student, "program": program},
        pluck="enrollment_date",
        order_by="enrollment_date asc",
        limit=1,
    )
    return {
        "id": student,
        "name": s.student_name or "",
        "legacy_number": s.legacy_student_number or "",
        "national_id": s.national_id or "",
        "dob": _fmt_date(s.date_of_birth),
        "birth_place": s.birth_place_ak or "",
        "image": s.image or "",
        "program": program or "",
        "department": dept,
        "degree": _settings().degree_name,
        "enrollment_date": _fmt_date(enrollment[0] if enrollment else None),
        "graduation_date": _fmt_date(s.graduation_date_ak),
        "registration_number": s.legacy_student_number or student,
    }


# ---------------------------------------------------------------------------
# جلب النتائج
# ---------------------------------------------------------------------------

def _fetch_results(student, program):
    fields = ["name", "course", "total_score", "academic_term", "program"]
    if frappe.db.has_column("Assessment Result", "score_preliminary_ak"):
        fields.append("score_preliminary_ak")
    if frappe.db.has_column("Assessment Result", "score_final_ak"):
        fields.append("score_final_ak")
    filters = {"student": student, "docstatus": 1}
    if program:
        filters["program"] = program
    return frappe.get_all(
        "Assessment Result", filters=filters, fields=fields, order_by="creation asc"
    )


def _ssr_by_term(student):
    out = {}
    for r in frappe.get_all(
        "Student Semester Result",
        filters={"student": student, "docstatus": 1},
        fields=[
            "academic_term",
            "semester_units",
            "semester_points",
            "semester_average",
            "cumulative_units",
            "cumulative_points",
            "cumulative_average",
            "status",
            "note",
        ],
    ):
        out.setdefault(r.academic_term, r)
    return out


def _build_blocks(student, program):
    """جداول الفصول: صفوف المواد + المجموع الفصلي والتراكمي لكل فصل."""
    courses = _course_map()
    results = _fetch_results(student, program)
    ssr_map = _ssr_by_term(student)

    by_term = {}
    for r in results:
        by_term.setdefault(r.academic_term, []).append(r)

    term_cache = {}
    terms = sorted(by_term, key=lambda t: rules._term_rank(t, term_cache))

    entries = []
    for r in results:
        c = courses.get(r.course)
        entries.append(
            {
                "course": r.course,
                "units": float((c.units if c else 0) or 0),
                "score": float(r.total_score or 0),
                "academic_term": r.academic_term,
            }
        )

    blocks = []
    for idx, term in enumerate(terms, start=1):
        dedup = {}
        for r in by_term[term]:
            score = float(r.total_score or 0)
            if r.course not in dedup or score > dedup[r.course]["score"]:
                c = courses.get(r.course)
                dedup[r.course] = {
                    "course": r.course,
                    "code": (c.course_code if c else "") or "",
                    "name": (c.course_name if c else r.course) or r.course,
                    "units": float((c.units if c else 0) or 0),
                    "score": score,
                    "semi": r.get("score_preliminary_ak"),
                    "fine": r.get("score_final_ak"),
                }
        rows = sorted(dedup.values(), key=lambda x: (x["code"], x["name"]))
        for i, row in enumerate(rows, start=1):
            row["idx"] = i
            row["grade"] = rules.grade_label(row["score"])
            row["points"] = fmt(round(row["score"] * row["units"], 2))
            row["total"] = fmt(row["score"])
            row["semi"] = fmt(row["semi"]) if row["semi"] not in (None, "") else ""
            row["fine"] = fmt(row["fine"]) if row["fine"] not in (None, "") else ""
            row["note"] = "" if row["score"] >= _settings().pass_score else "راسب"

        agg = rules.aggregate_averages(entries, current_term=term)
        ssr = ssr_map.get(term)

        def _pick(field, fallback):
            if ssr and ssr.get(field) is not None:
                return fmt(ssr.get(field))
            return fmt(fallback)

        semester = {
            "units": _pick("semester_units", agg["semester_units"]),
            "points": _pick("semester_points", agg["semester_points"]),
            "average": _pick("semester_average", agg["semester_average"]),
        }
        cumulative = {
            "units": _pick("cumulative_units", agg["cumulative_units"]),
            "points": _pick("cumulative_points", agg["cumulative_points"]),
            "average": _pick("cumulative_average", agg["cumulative_average"]),
        }
        ay, season, year = _split_term(term)
        blocks.append(
            {
                "index": idx,
                "term": term,
                "academic_year": ay,
                "season": season,
                "year": year,
                "label": f"{season} {year}".strip(),
                "rows": rows,
                "semester": semester,
                "cumulative": cumulative,
                "status": (ssr.status if ssr else agg["status"]) or "",
            }
        )
    return blocks


def _cumulative_summary(blocks):
    if not blocks:
        return {"units": "", "points": "", "average": "", "grade": ""}
    cum = blocks[-1]["cumulative"]
    try:
        avg = float(cum["average"] or 0)
    except (TypeError, ValueError):
        avg = 0.0
    return {
        "units": cum["units"],
        "points": cum["points"],
        "average": cum["average"],
        "grade": rules.grade_label(avg) if avg else "",
    }


# ---------------------------------------------------------------------------
# السياقات الأربعة (تُنادى من قوالب الطباعة)
# ---------------------------------------------------------------------------

def transcript_context(student, program=None):
    """كشف الدرجات — بيانات الترويسة + جداول كل الفصول + المجموع التراكمي."""
    program = _resolve_program(student, program)
    blocks = _build_blocks(student, program)
    return {
        "student": student_info(student, program),
        "blocks": blocks,
        "result": _cumulative_summary(blocks),
        "today": _fmt_date(frappe.utils.nowdate()),
    }


def final_result_context(student, program=None):
    """نموذج النتيجة — نفس الجداول + صندوق النتيجة النهائية."""
    return transcript_context(student, program)


def notice_context(ssr_name):
    """إشعار النتيجة الفصلي — سجل SSR واحد (طالب/فصل)."""
    doc = frappe.get_doc("Student Semester Result", ssr_name)
    program = _resolve_program(doc.student, doc.program or None)
    blocks = _build_blocks(doc.student, program)
    block = next((b for b in blocks if b["term"] == doc.academic_term), None)
    ay, season, year = _split_term(doc.academic_term)
    average = ""
    if doc.semester_average is not None:
        average = fmt(doc.semester_average)
    elif block:
        average = block["semester"]["average"]
    return {
        "student": student_info(doc.student, program),
        "block": block,
        "academic_year": ay,
        "season": season,
        "year": year,
        "average": average,
        "status": doc.status or "",
        "note": doc.note or "",
    }


def card_context(student, program=None):
    """بطاقة الطالب الدراسية — سطر لكل مادة مع تقدير الفصلين والنتيجة النهائية."""
    program = _resolve_program(student, program)
    courses = _course_map()
    results = _fetch_results(student, program)
    pc_sem = {
        r.course: (r.semester or 99)
        for r in frappe.get_all(
            "Program Course", filters={"parent": program}, fields=["course", "semester"]
        )
    }

    best = {}
    for r in results:
        score = float(r.total_score or 0)
        _ay, season, _year = _split_term(r.academic_term)
        b = best.setdefault(r.course, {"best": None, "p1": None, "p2": None})
        if b["best"] is None or score > b["best"]:
            b["best"] = score
        if season == "ربيع":
            if b["p2"] is None or score > b["p2"]:
                b["p2"] = score
        else:
            if b["p1"] is None or score > b["p1"]:
                b["p1"] = score

    rows = []
    for cname, b in best.items():
        c = courses.get(cname)
        units = float((c.units if c else 0) or 0)
        score = float(b["best"] or 0)
        rows.append(
            {
                "course": cname,
                "code": (c.course_code if c else "") or "",
                "name": (c.course_name if c else cname) or cname,
                "units": fmt(units),
                "p1": rules.grade_label(b["p1"]) if b["p1"] is not None else "",
                "p2": rules.grade_label(b["p2"]) if b["p2"] is not None else "",
                "score": fmt(score),
                "grade": rules.grade_label(score),
                "points": fmt(round(score * units, 2)),
                "note": "" if score >= _settings().pass_score else "راسب",
            }
        )
    rows.sort(key=lambda x: (pc_sem.get(x["course"], 99), x["code"], x["name"]))
    for i, row in enumerate(rows, start=1):
        row["idx"] = i

    blocks = _build_blocks(student, program)
    return {
        "student": student_info(student, program),
        "rows": rows,
        "result": _cumulative_summary(blocks),
        "today": _fmt_date(frappe.utils.nowdate()),
    }
