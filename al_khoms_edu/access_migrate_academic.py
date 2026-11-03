# -*- coding: utf-8 -*-
"""ترحيل قسم الحاسوب - البيانات الأكاديمية.

يقرأ جدول `degree` من قاعدة Access القديمة وينشئ:
  - Program Enrollment لكل (طالب، برنامج، سنة أكاديمية)
  - Course Enrollment لكل مادة
  - Student Group / Assessment Plan / Assessment Result للدرجات
  - Student Semester Result بالمعدل الفصلي والتراكمي مع المعادلة
  - Student Attempt Log لعداد المحاولات

قواعد الدرجات القديمة: أعمال الفصل (semi) 40% + النهائي (fine) 60% =
المجموع (tot) درجة مرجّحة 0-100، النجاح >= 50.
"""

import frappe

from al_khoms_edu.access_migrate_computer import (
    ar,
    get_program,
    load_degree,
    map_subject_code,
    time_to_term_name,
)
from al_khoms_edu import academic_rules as rules

GRADE_SCALE      = "نظام ليبي"
CRITERIA         = "الامتحان النهائي والأعمال"
ASSESSMENT_GROUP = "All Assessment Groups"
MAX_SCORE        = 100.0

GRADE_INTERVALS = [
    ("راسب",     0),
    ("مقبول",   50),
    ("جيد",     65),
    ("جيد جداً", 75),
    ("ممتاز",   85),
]

EXTRA_ALT_CODES = {
    "CP232":  "البرمجة الشيئية",
    "CP234":  "تحليل وتصميم نظم",
    "CP244":  "تراكيب البيانات والخوارزميات",
    "CP1126": "نظم تشغيل الحاسبات",
    "CD233":  "قواعد بيانات II",
    "CD243":  "البرمجة بتقنية DBMS",
}

COURSE_CW125 = {
    "course_name":  "الوسائط المتعددة",
    "course_code":  "CW125",
    "units":        4,
    "program_name": "قواعد البيانات",
    "semester":     4,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def normalize_code(code):
    c = ar(code).upper().replace(" ", "").strip()
    return map_subject_code(c)


def normalize_year(yr_no):
    s = str(ar(yr_no) or "").strip()
    parts = s.split("/")
    try:
        a = int(parts[0])
    except (ValueError, IndexError):
        return None
    if len(parts) > 1 and parts[1].strip().isdigit():
        start = int(parts[1])
    else:
        start = a - 1
    if not (2000 <= start <= 2100):
        return None
    return f"{a}/{start}"


def term_name_for(ay_name, term_ar):
    parts = str(ay_name).split("/")
    start = parts[1] if len(parts) > 1 else parts[0]
    return f"{ay_name} ({term_ar} {start})"


def grade_letter(score):
    try:
        score = float(score or 0)
    except (TypeError, ValueError):
        score = 0
    for name, threshold in reversed(GRADE_INTERVALS):
        if score >= threshold:
            return name
    return "راسب"


# ---------------------------------------------------------------------------
# foundation
# ---------------------------------------------------------------------------

def ensure_alt_codes():
    created = 0
    for code, course_name in EXTRA_ALT_CODES.items():
        if not frappe.db.exists("Course", course_name):
            print("!! course missing for alt code", code, course_name)
            continue
        if frappe.db.exists("Course Alternate Code", {"parent": course_name, "code": code}):
            continue
        parent = frappe.get_doc("Course", course_name)
        parent.append("course_codes", {"code": code, "code_type": "بديل"})
        parent.save(ignore_permissions=True)
        created += 1
    frappe.db.commit()
    print("alt codes added:", created)
    return created


def ensure_course_cw125():
    c = COURSE_CW125
    if not frappe.db.exists("Course", c["course_name"]):
        doc = frappe.new_doc("Course")
        doc.course_name = c["course_name"]
        doc.course_code = c["course_code"]
        doc.units       = c["units"]
        doc.is_general  = 0
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("created course:", c["course_name"])

    prog = frappe.get_doc("Program", c["program_name"])
    if not any(r.course == c["course_name"] for r in prog.courses):
        prog.append("courses", {
            "course":      c["course_name"],
            "course_name": c["course_name"],
            "semester":    c["semester"],
            "required":    1,
        })
        prog.save(ignore_permissions=True)
        frappe.db.commit()
        print("added", c["course_name"], "to program", c["program_name"])


def ensure_grading_scale():
    if frappe.db.exists("Grading Scale", GRADE_SCALE):
        return
    doc = frappe.new_doc("Grading Scale")
    doc.grading_scale_name = GRADE_SCALE
    for grade, threshold in GRADE_INTERVALS:
        doc.append("intervals", {
            "grade_code": grade, "threshold": threshold, "grade_description": grade,
        })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("created grading scale:", GRADE_SCALE)


def ensure_criteria():
    if frappe.db.exists("Assessment Criteria", CRITERIA):
        return
    doc = frappe.new_doc("Assessment Criteria")
    doc.criteria_name  = CRITERIA
    doc.maximum_score  = MAX_SCORE
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("created assessment criteria:", CRITERIA)


def ensure_years_and_terms():
    rows = load_degree()
    years = set()
    for r in rows:
        ay = normalize_year(r.get("yr_no"))
        if ay:
            years.add(ay)
    created_y = created_t = 0
    for ay in sorted(years):
        end, start = ay.split("/")
        if not frappe.db.exists("Academic Year", ay):
            doc = frappe.new_doc("Academic Year")
            doc.academic_year_name = ay
            doc.year_start_date    = f"{start}-09-01"
            doc.year_end_date      = f"{end}-06-30"
            doc.insert(ignore_permissions=True)
            created_y += 1
        for term_ar, s, e in (
            ("خريف", f"{start}-09-01", f"{start}-12-31"),
            ("ربيع",  f"{end}-01-15",  f"{end}-05-31"),
        ):
            name = term_name_for(ay, term_ar)
            if frappe.db.exists("Academic Term", name):
                continue
            doc = frappe.new_doc("Academic Term")
            doc.academic_year   = ay
            doc.term_name       = name
            doc.term_start_date = s
            doc.term_end_date   = e
            doc.insert(ignore_permissions=True)
            created_t += 1
    frappe.db.commit()
    print("years:", created_y, "| terms:", created_t, "| total years:", len(years))


def run_foundation():
    ensure_alt_codes()
    ensure_course_cw125()
    ensure_grading_scale()
    ensure_criteria()
    ensure_years_and_terms()


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------

def _code_map():
    m = {}
    for c in frappe.get_all("Course", fields=["name", "course_code"]):
        if c.course_code:
            m[c.course_code] = c.name
    for ac in frappe.get_all("Course Alternate Code", fields=["parent", "code"]):
        if ac.code:
            m.setdefault(ac.code, ac.parent)
    return m


def load_entries():
    codes = _code_map()
    out = []
    skipped_no_course = {}
    skipped_empty = 0
    for r in load_degree():
        program = get_program(r.get("dept_type"))
        if not program:
            continue
        ay      = normalize_year(r.get("yr_no"))
        term_ar = time_to_term_name(r.get("time"))
        if not ay or not term_ar:
            continue
        stud_number = r.get("stud_number") or ""
        if not stud_number:
            continue
        term = term_name_for(ay, term_ar)
        for i in range(1, 14):
            raw = r.get(f"sub_no{i}") or ""
            s   = str(raw).strip()
            if not s or s == "0":
                continue
            try:
                unit = float(r.get(f"unit{i}") or 0)
                semi = float(r.get(f"semi{i}") or 0)
                fine = float(r.get(f"fine{i}") or 0)
                tot  = float(r.get(f"tot{i}")  or 0)
            except (TypeError, ValueError):
                continue
            if not (unit or semi or fine or tot):
                skipped_empty += 1
                continue
            nc     = normalize_code(s)
            course = codes.get(nc)
            if not course:
                skipped_no_course[nc] = skipped_no_course.get(nc, 0) + 1
                continue
            out.append({
                "stud_number":  stud_number,
                "program":      program,
                "academic_year": ay,
                "term":         term,
                "term_ar":      term_ar,
                "course":       course,
                "unit":         unit,
                "semi":         semi,
                "fine":         fine,
                "tot":          tot,
                "sub_type":     ar(r.get(f"sub_type{i}") or ""),
            })
    print(
        "entries:", len(out),
        "| skipped empty:", skipped_empty,
        "| skipped unknown code:", skipped_no_course or "none",
    )
    return out


def _student_map():
    return {
        s.legacy_student_number: s.name
        for s in frappe.get_all("Student", fields=["name", "legacy_student_number"])
        if s.legacy_student_number
    }


# ---------------------------------------------------------------------------
# enrollments
# ---------------------------------------------------------------------------

def run_enrollments(entries=None):
    frappe.flags.in_import = True
    if entries is None:
        entries = load_entries()
    students  = _student_map()
    pe_cache  = {}
    ce_exists = set()
    missing_students = set()
    created_pe = created_ce = 0

    for e in entries:
        student = students.get(e["stud_number"])
        if not student:
            missing_students.add(e["stud_number"])
            continue
        pe_key = (student, e["program"], e["academic_year"])
        if pe_key not in pe_cache:
            existing = frappe.get_all(
                "Program Enrollment",
                filters={"student": student, "program": e["program"], "academic_year": e["academic_year"]},
                pluck="name", limit=1,
            )
            if existing:
                pe_cache[pe_key] = existing[0]
            else:
                start = e["academic_year"].split("/")[1]
                doc = frappe.new_doc("Program Enrollment")
                doc.student         = student
                doc.program         = e["program"]
                doc.academic_year   = e["academic_year"]
                doc.enrollment_date = f"{start}-09-01"
                doc.student_name    = frappe.db.get_value("Student", student, "student_name")
                doc.insert(ignore_permissions=True)
                pe_cache[pe_key] = doc.name
                created_pe += 1
                if created_pe % 25 == 0:
                    frappe.db.commit()

        pe     = pe_cache[pe_key]
        ce_key = (pe, e["course"])
        if ce_key in ce_exists:
            continue
        if frappe.get_all("Course Enrollment", filters={"program_enrollment": pe, "course": e["course"]}, limit=1):
            ce_exists.add(ce_key)
            continue
        start = e["academic_year"].split("/")[1]
        doc = frappe.new_doc("Course Enrollment")
        doc.program_enrollment = pe
        doc.student            = student
        doc.course             = e["course"]
        doc.enrollment_date    = f"{start}-09-01"
        doc.insert(ignore_permissions=True)
        ce_exists.add(ce_key)
        created_ce += 1
        if created_ce % 50 == 0:
            frappe.db.commit()

    frappe.db.commit()
    print(
        "PE created:", created_pe, "| CE created:", created_ce,
        "| missing students:", missing_students or "none",
    )
    return {"pe": created_pe, "ce": created_ce}


# ---------------------------------------------------------------------------
# assessment results
# ---------------------------------------------------------------------------

def _ensure_student_group(program, ay, term_ar, students):
    name = f"{program} - {ay} - {term_ar}"
    if frappe.db.exists("Student Group", name):
        return name
    doc = frappe.new_doc("Student Group")
    doc.student_group_name = name
    doc.academic_year      = ay
    doc.group_based_on     = "Student Group"
    doc.program            = program
    for student in sorted(students):
        doc.append("students", {"student": student})
    doc.academic_term = term_name_for(ay, "خريف" if term_ar == "خريف" else "ربيع")
    doc.insert(ignore_permissions=True)
    return name


def _ensure_assessment_plan(course, program, ay, term, sg):
    existing = frappe.get_all(
        "Assessment Plan",
        filters={"course": course, "academic_term": term, "student_group": sg},
        pluck="name", limit=1,
    )
    if existing:
        return existing[0]
    end, start = ay.split("/")
    sched = f"{start}-12-15" if "خريف" in term else f"{end}-05-15"
    doc = frappe.new_doc("Assessment Plan")
    doc.assessment_name          = f"{course} - {term}"
    doc.student_group            = sg
    doc.assessment_group         = ASSESSMENT_GROUP
    doc.grading_scale            = GRADE_SCALE
    doc.program                  = program
    doc.course                   = course
    doc.academic_year            = ay
    doc.academic_term            = term
    doc.schedule_date            = sched
    doc.from_time                = "09:00:00"
    doc.to_time                  = "12:00:00"
    doc.maximum_assessment_score = MAX_SCORE
    doc.append("assessment_criteria", {"assessment_criteria": CRITERIA, "maximum_score": MAX_SCORE})
    doc.insert(ignore_permissions=True)
    return doc.name


def run_results(entries=None):
    frappe.flags.in_import = True
    if entries is None:
        entries = load_entries()
    students = _student_map()

    groups = {}
    for e in entries:
        student = students.get(e["stud_number"])
        if not student:
            continue
        key = (e["program"], e["academic_year"], e["term_ar"])
        groups.setdefault(key, set()).add(student)

    sg_cache = {}
    for key, members in groups.items():
        sg_cache[key] = _ensure_student_group(*key, members)
    frappe.db.commit()
    print("student groups:", len(sg_cache))

    ap_cache = {}
    for e in entries:
        student = students.get(e["stud_number"])
        if not student:
            continue
        sg_key = (e["program"], e["academic_year"], e["term_ar"])
        ap_key = (e["course"], e["academic_year"], e["term"])
        if ap_key not in ap_cache:
            ap_cache[ap_key] = _ensure_assessment_plan(
                e["course"], e["program"], e["academic_year"], e["term"], sg_cache[sg_key],
            )
    frappe.db.commit()
    print("assessment plans:", len(ap_cache))

    created_ar = skipped = 0
    for e in entries:
        student = students.get(e["stud_number"])
        if not student:
            skipped += 1
            continue
        ap = ap_cache.get((e["course"], e["academic_year"], e["term"]))
        if not ap:
            skipped += 1
            continue
        if frappe.db.exists("Assessment Result", {"assessment_plan": ap, "student": student}):
            skipped += 1
            continue
        sg     = sg_cache[(e["program"], e["academic_year"], e["term_ar"])]
        letter = grade_letter(e["tot"])
        doc = frappe.new_doc("Assessment Result")
        doc.assessment_plan  = ap
        doc.student          = student
        doc.student_name     = frappe.db.get_value("Student", student, "student_name")
        doc.program          = e["program"]
        doc.course           = e["course"]
        doc.academic_year    = e["academic_year"]
        doc.academic_term    = e["term"]
        doc.student_group    = sg
        doc.assessment_group = ASSESSMENT_GROUP
        doc.grading_scale    = GRADE_SCALE
        doc.maximum_score    = MAX_SCORE
        doc.total_score      = e["tot"]
        doc.grade            = letter
        doc.comment          = e["sub_type"]
        doc.append("details", {
            "assessment_criteria": CRITERIA,
            "maximum_score": MAX_SCORE,
            "score": e["tot"],
            "grade": letter,
        })
        doc.insert(ignore_permissions=True)
        # النتيجة التاريخية تُعتمد فوراً؛ المسودات لا تدخل المعدل ولا المحاولات.
        doc.submit()
        created_ar += 1
        if created_ar % 25 == 0:
            frappe.db.commit()

    frappe.db.commit()
    print("assessment results created:", created_ar, "| skipped:", skipped)
    return {"created": created_ar, "skipped": skipped}


# ---------------------------------------------------------------------------
# Student Semester Result — مع احتساب مواد المعادلة § 2.7
# ---------------------------------------------------------------------------

def _academic_status(sem_avg, cum_avg):
    """حالة الفصل — موحّدة مع المحرك الرسمي (إنذار عند تراكمي < 55%)."""
    return rules.status_for(sem_avg, cum_avg)


def run_semester_results(entries=None):
    """
    يحسب المعدل الفصلي والتراكمي لكل طالب.

    § 2.7: مواد المعادلة تدخل في حساب المعدل التراكمي.
    الحساب التراكمي يأخذ أعلى درجة للمادة في حالة الإعادة.
    """
    frappe.flags.in_import = True
    if entries is None:
        entries = load_entries()

    students = _student_map()

    # تجميع فصلي
    from collections import defaultdict
    buckets = defaultdict(list)
    for e in entries:
        student = students.get(e["stud_number"])
        if not student:
            continue
        key = (student, e["program"], e["academic_year"], e["term"])
        buckets[key].append({"unit": e["unit"], "tot": e["tot"], "course": e["course"]})

    # ترتيب الفصول زمنياً لكل (طالب، تخصص)
    student_terms = defaultdict(list)
    for (student, program, ay, term) in buckets:
        student_terms[(student, program)].append((ay, term))
    for key in student_terms:
        student_terms[key].sort()

    created = updated = 0

    for (student, program) in student_terms:
        # ابدأ بمواد المعادلة في الحساب التراكمي
        equiv_entries = rules.get_equivalence_entries(student)
        cum_units  = sum(float(eq["units"] or 0) for eq in equiv_entries)
        cum_points = sum(
            float(eq["grade"] or 0) * float(eq["units"] or 0)
            for eq in equiv_entries
        )
        cum_accomplished = sum(
            float(eq["units"] or 0)
            for eq in equiv_entries
            if float(eq["grade"] or 0) >= rules.PASS_SCORE
        )
        # كل مادة مرّت على الطالب (أعلى درجة لها)
        best_scores = {eq["course"]: float(eq["grade"] or 0) for eq in equiv_entries}

        for (ay, term) in student_terms[(student, program)]:
            key  = (student, program, ay, term)
            rows = buckets[key]

            sem_units  = sum(r["unit"] for r in rows)
            sem_points = sum(r["tot"] * r["unit"] for r in rows)
            sem_avg    = (sem_points / sem_units) if sem_units else 0.0

            # تحديث best_scores — الإعادة تؤخذ الأعلى
            for r in rows:
                c, sc = r["course"], r["tot"]
                if c not in best_scores or sc > best_scores[c]:
                    # أضف الفرق في النقاط
                    old_contribution = best_scores.get(c, 0) * r["unit"]
                    new_contribution = sc * r["unit"]
                    if c not in best_scores:
                        cum_units      += r["unit"]
                        cum_points     += new_contribution
                    else:
                        cum_points += new_contribution - old_contribution
                    best_scores[c] = sc

            cum_accomplished = sum(
                frappe.db.get_value("Course", c, "units") or 0
                for c, sc in best_scores.items()
                if sc >= rules.PASS_SCORE
            )

            cum_avg = (cum_points / cum_units) if cum_units else 0.0
            status  = _academic_status(sem_avg, cum_avg)

            existing = frappe.get_all(
                "Student Semester Result",
                filters={"student": student, "program": program, "academic_year": ay, "academic_term": term},
                pluck="name", limit=1,
            )

            data = {
                "semester_units":     sem_units,
                "semester_points":    round(sem_points, 2) if sem_units else 0,
                "semester_average":   round(sem_avg, 2),
                "cumulative_units":   cum_units,
                "cumulative_points":  round(cum_points, 2),
                "cumulative_average": round(cum_avg, 2),
                "accomplished_units": cum_accomplished,
                "status":             status,
            }

            if existing:
                doc = frappe.get_doc("Student Semester Result", existing[0])
                for k, v in data.items():
                    doc.set(k, v)
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.new_doc("Student Semester Result")
                doc.student       = student
                doc.program       = program
                doc.academic_year = ay
                doc.academic_term = term
                for k, v in data.items():
                    doc.set(k, v)
                doc.insert(ignore_permissions=True)
                created += 1

            if (created + updated) % 50 == 0:
                frappe.db.commit()

    frappe.db.commit()
    print("SSR → created:", created, "| updated:", updated,
          "| total:", frappe.db.count("Student Semester Result"))
    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def run_academic():
    """الترحيل الأكاديمي الكامل لقسم الحاسوب."""
    run_foundation()
    entries = load_entries()
    run_enrollments(entries)
    run_results(entries)
    run_semester_results(entries)
    # بناء عداد المحاولات من البيانات المرحّلة
    rules.build_attempt_log_from_history()
    print("\n✓ اكتمل الترحيل الأكاديمي الكامل.")
