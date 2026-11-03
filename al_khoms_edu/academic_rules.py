# -*- coding: utf-8 -*-
"""
academic_rules.py
=================
محرك القواعد الأكاديمية للمعهد العالي للعلوم والتقنية — الخمس.

يُغلّف كل القواعد المتفق عليها في ملف المشروع الرئيسي:
  § 2.2  المواد الاعتمادية (Prerequisites)
  § 2.3  قاعدة الترقية (نهاية الفصل)
  § 2.6  عدد محاولات المادة
  § 2.7  المعادلة واحتساب درجاتها في المعدل التراكمي

استخدام:
    bench --site erp.local execute al_khoms_edu.academic_rules.<function>

أو من داخل الكود:
    from al_khoms_edu import academic_rules as ar
"""

import re

import frappe
from frappe import _

PASS_SCORE = 50.0   # حد النجاح — م21/م33 (fallback)
MAX_ATTEMPTS = 3    # الحد العادي (المحاولة 4 استثنائية بموافقة الإدارة) — م37 (fallback)
EXPULSION_ATTEMPT = 4   # الرسوب في 4 محاولات متتالية → فصل — م37 (fallback)
PROJECT_PASS_SCORE = 65.0   # نسبة النجاح في مشروع التخرج — م46 (fallback)
GRADUATION_MIN_AVG = 55.0   # الحد الأدنى للمعدل التراكمي للتأهل للمشروع والتخرج — م43/م44 (fallback)

# ---------------------------------------------------------------------------
# قواعد دراسية — قراءة من مستند الإعدادات مع fallback للقيم الافتراضية
# ---------------------------------------------------------------------------

_RULES_CACHE = None


def get_rules():
    """يُعيد قواعد الدراسية من مستند «Academic Rules Settings» (Single).

    إذا كان المستند غير موجود أو حقل فارغ، يستخدم القيم الافتراضية في الكود.
    """
    global _RULES_CACHE
    if _RULES_CACHE is not None:
        return _RULES_CACHE

    defaults = frappe._dict(
        pass_score=PASS_SCORE,
        max_attempts=MAX_ATTEMPTS,
        expulsion_attempt=EXPULSION_ATTEMPT,
        second_failure_warning=2,
        max_fail_before_repeat=2,
        cum_alert_threshold=55.0,
        very_weak_threshold=35.0,
        project_pass_score=PROJECT_PASS_SCORE,
        graduation_min_avg=GRADUATION_MIN_AVG,
        degree_name="الدبلوم العالي",
        phone_numbers="",
        logo_size=78,
        student_photo_size=78,
        page_margin="10mm 8mm",
        attempt_status_available="متاح",
        attempt_status_approval="تحتاج موافقة",
        attempt_status_expulsion="فصل",
        attempt_status_passed="ناجح",
        semester_status_alert="إنذار",
        semester_status_repeat="إعادة",
        semester_status_normal="طبيعي",
        promotion_promoted="ترقية",
        promotion_carry="ترقية مع ترحيل",
        promotion_repeat="إعادة فصل",
        suspension_status="موقوف",
        fall_month="09",
        spring_month="02",
    )

    try:
        doc = frappe.get_single("Academic Rules Settings")
        for key in defaults:
            val = doc.get(key)
            if val not in (None, ""):
                defaults[key] = val
    except Exception:
        pass

    _RULES_CACHE = defaults
    return _RULES_CACHE


def reset_rules_cache():
    """يلغي ذاكرة قواعد الدراسية (تُستدعى عند تعديل الإعدادات أو في الدفعات)."""
    global _RULES_CACHE
    _RULES_CACHE = None


# ============================================================
# § 2.2  المواد الاعتمادية
# ============================================================

def get_student_program(student, program_name=None):
    """يُعيد البرنامج الصريح أو آخر برنامج مسجَّل للطالب.

    تُستخدم هذه الدالة من التسجيل والتقييم معاً حتى لا يختلف تفسير
    البرنامج بين الشاشتين.
    """
    if program_name:
        return program_name
    if not student:
        return None

    rows = frappe.get_all(
        "Program Enrollment",
        filters={"student": student, "docstatus": ["<", 2]},
        fields=["program"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0].program if rows else None


def student_is_exempt(student):
    """هل الطالب مستثنى صراحة من فحص المتطلبات؟ (حقل Student.exempt)."""
    if not student or not frappe.get_meta("Student").has_field("exempt"):
        return False
    return bool(frappe.db.get_value("Student", student, "exempt"))


def get_prerequisites(program_name, course_name):
    """
    § 2.2 — المتطلبات الإلزامية للمادة، من المصدرين المعتمدين معاً:

    1. متطلبات على مستوى المادة: Course.pre_requisite_courses.
    2. متطلبات على مستوى البرنامج: Program.prerequisites.

    يُستخدم حقل Program Course.prerequisite_course القديم كاحتياط فقط
    إذا لم توجد متطلبات حديثة، حفاظاً على البيانات التاريخية.

    Returns: list[str] — أسماء المواد المتطلبة (بلا تكرار).
    """
    if not course_name:
        return []

    prereqs = set()

    # 1) متطلبات المادة نفسها
    if frappe.get_meta("Course").has_field("pre_requisite_courses"):
        for row in frappe.get_all(
            "Course Prerequisite",
            filters={
                "parent": course_name,
                "parenttype": "Course",
                "parentfield": "pre_requisite_courses",
            },
            fields=["course"],
        ):
            if row.course:
                prereqs.add(row.course)

    # 2) متطلبات البرنامج للمادة نفسها — الإلزامي فقط
    if program_name:
        for row in frappe.get_all(
            "Program Prerequisite",
            filters={
                "parent": program_name,
                "parenttype": "Program",
                "course": course_name,
            },
            fields=["prerequisite_course", "prerequisite_type"],
        ):
            if row.prerequisite_course and (
                not row.prerequisite_type or row.prerequisite_type == "إلزامي"
            ):
                prereqs.add(row.prerequisite_course)

        # 3) احتياط تاريخي: لا يُضاف إلا إذا لم توجد متطلبات حديثة
        if not prereqs:
            old = frappe.db.get_value(
                "Program Course",
                {"parent": program_name, "course": course_name},
                "prerequisite_course",
            )
            if old:
                prereqs.add(old)

    return sorted(prereqs)


def has_passed_course(student, course_name, pass_score=None):
    """هل اجتاز الطالب المادة بنتيجة **مرحّلة** أو معادلة **مرحّلة**؟

    لا تُحتسب المسودات ولا السجلات الملغاة. هذه هي الدالة الوحيدة التي
    تستخدمها المتطلبات والمعدل التراكمي لمعرفة النجاح.
    """
    if not student or not course_name:
        return False

    ps = float(pass_score if pass_score is not None else get_rules().pass_score)
    if frappe.db.exists(
        "Assessment Result",
        {
            "student": student,
            "course": course_name,
            "total_score": [">=", ps],
            "docstatus": 1,
        },
    ):
        return True

    return bool(
        frappe.db.exists(
            "Student Equivalence",
            {
                "student": student,
                "course": course_name,
                "grade": [">=", ps],
                "docstatus": 1,
            },
        )
    )


def check_prerequisites_met(student, program_name, course_name):
    """
    § 2.2 — هل اجتاز الطالب كل المتطلبات السابقة للمادة؟

    يستخدم نفس المصدرين ونفس دالة النجاح في التسجيل وتقييد الدرجة.

    Returns:
        (True, [])                إذا اجتاز الكل أو كان مستثنى
        (False, [missing, ...])   قائمة المواد غير المجتازة
    """
    if student_is_exempt(student):
        return True, []

    prereqs = get_prerequisites(program_name, course_name)
    if not prereqs:
        return True, []

    ps = get_rules().pass_score
    missing = [course for course in prereqs if not has_passed_course(student, course, ps)]

    return (len(missing) == 0), missing


# ============================================================
# § 2.3  قاعدة الترقية
# ============================================================

def get_semester_failed_courses(student, program_name, academic_year, academic_term):
    """
    يُعيد المواد الراسبة للطالب في فصل محدد.

    تعتمد النتيجة **المرحّلة فقط**، وتأخذ أفضل محاولة لكل مادة داخل الفصل
    (فلا تُحتسب مادة رُسبت ثم نجح الطالب فيها في المحاولة التالية).
    """
    results = frappe.get_all(
        "Assessment Result",
        filters={
            "student":       student,
            "academic_year": academic_year,
            "academic_term": academic_term,
            "docstatus":     1,
        },
        fields=["course", "total_score", "program"],
    )
    results = [
        r
        for r in results
        if not program_name or not r.program or r.program == program_name
    ]
    ps = get_rules().pass_score
    best = {}
    for r in results:
        if r.total_score in (None, ""):
            continue
        score = float(r.total_score)
        if r.course not in best or score > best[r.course]:
            best[r.course] = score

    return sorted(
        course
        for course, score in best.items()
        if score < ps and not has_passed_course(student, course, ps)
    )


def _latest_submitted_term(student, program_name, target_term=None):
    """آخر فصل دراسي له نتائج مرحّلة، مع عدم تجاوز الفصل المستهدف إن حُدِّد."""
    rows = frappe.get_all(
        "Assessment Result",
        filters={"student": student, "docstatus": 1},
        fields=["program", "academic_year", "academic_term"],
        order_by="creation asc",
    )
    rows = [
        r
        for r in rows
        if r.academic_term
        and (not program_name or not r.program or r.program == program_name)
    ]
    if not rows:
        return None, None

    cache = {}
    target_rank = _term_rank(target_term, cache) if target_term else None
    candidates = []
    for r in rows:
        if target_rank is None or _term_rank(r.academic_term, cache) <= target_rank:
            candidates.append(r)
    if not candidates:
        return None, None

    latest = max(candidates, key=lambda r: _term_rank(r.academic_term, cache))
    return latest.academic_term, latest.academic_year


def get_repeat_courses(student, program_name, target_term=None):
    """
    المواد التي يجب إعادتها فقط عند صدور قرار «إعادة فصل».

    القاعدة قرار **نهاية فصل** وليست منعاً للتسجيل؛ لذلك تُستدعى عند تجهيز
    تسجيل الفصل التالي/الإعادة، ولا تمنع إنشاء Program Enrollment.
    """
    source_term, source_year = _latest_submitted_term(
        student, program_name, target_term=target_term
    )
    if not source_term:
        return []

    decision = get_promotion_decision(
        student, program_name, source_year, source_term
    )
    if decision["decision"] != get_rules().promotion_repeat:
        return []
    return decision["failed_courses"]


def prepare_repeat_term_courses(doc, method=None):
    """
    يُقيّد Program Enrollment الجديد، عند وجود قرار «إعادة فصل»، على المواد
    الراسبة فقط. لا يمنع الإنشاء ولا يمسّ التسجيلات القائمة.
    """
    if getattr(frappe.flags, "in_import", False) or getattr(
        frappe.flags, "in_migrate", False
    ):
        return []
    if not doc.is_new() or not doc.student or not doc.program or not doc.academic_term:
        return []

    failed = get_repeat_courses(doc.student, doc.program, target_term=doc.academic_term)
    if not failed:
        return []

    rows = []
    for course in failed:
        plan = frappe.db.get_value(
            "Program Course",
            {"parent": doc.program, "course": course},
            ["course_name"],
            as_dict=True,
        )
        course_name = (
            plan.course_name
            if plan and plan.course_name
            else frappe.db.get_value("Course", course, "course_name")
        )
        rows.append({"course": course, "course_name": course_name})

    doc.set("courses", [])
    for row in rows:
        doc.append("courses", row)

    frappe.msgprint(
        _(
            "قرار نهاية الفصل: إعادة المواد الراسبة فقط ({0}). "
            "تم تقييد تسجيل البرنامج على هذه المواد."
        ).format("، ".join(failed)),
        title=_("إعادة فصل"),
        indicator="orange",
        alert=True,
    )
    return failed


def get_promotion_decision(student, program_name, academic_year, academic_term):
    """
    قرار الترقية بعد نهاية الفصل — م16.

    - 0 راسب → «ترقية».
    - 1 أو 2 راسب مع معدل تراكمي ≥ 55% → «ترقية مع ترحيل» (نقل مادة/مادتين).
    - إلا (أكثر من مادتين، أو تراكمي < 55%) → «إعادة فصل».

    Returns dict:
        {
            "decision":           "ترقية" | "ترقية مع ترحيل" | "إعادة فصل",
            "failed_courses":     [...],
            "failed_count":       int,
            "cumulative_average": float,
        }
    """
    failed = get_semester_failed_courses(student, program_name, academic_year, academic_term)
    n = len(failed)
    cum_avg = _cumulative_average_up_to(student, program_name, academic_term)
    rules = get_rules()

    if n == 0:
        decision = rules.promotion_promoted
    elif n <= rules.max_fail_before_repeat and cum_avg >= rules.cum_alert_threshold:
        decision = rules.promotion_carry
    else:
        decision = rules.promotion_repeat

    repeat_required = decision == rules.promotion_repeat
    return {
        "decision":           decision,
        "failed_courses":     failed,
        "failed_count":       n,
        "cumulative_average": cum_avg,
        "repeat_required":    repeat_required,
        "repeat_courses":     list(failed) if repeat_required else [],
    }


_UNITS_CACHE = None


def reset_units_cache():
    """يُلغي ذاكرة وحدات المقررات (تُستدعى في بداية الدفعات المجدولة)."""
    global _UNITS_CACHE
    _UNITS_CACHE = None


def _get_course_units(course):
    """وحدات المقرر مع ذاكرة مستوى العملية — تجنّب استعلام لكل صف."""
    global _UNITS_CACHE
    if _UNITS_CACHE is None:
        _UNITS_CACHE = {
            r.name: float(r.units or 0)
            for r in frappe.get_all("Course", fields=["name", "units"])
        }
    return _UNITS_CACHE.get(course, 0.0)


def _result_entries(student, program=None, up_to_year=None):
    """يبني إدخالات المحرك الرسمي من النتائج **المرحّلة فقط**.

    - النتيجة الملغاة أو المسودة لا تدخل.
    - مواد المعادلة المرحّلة تُضاف مرة واحدة لكل مادة، بلا فصل، لتُحتسب
      في التراكمي فقط (م7/م40).
    """
    filters = {"student": student, "docstatus": 1}
    if up_to_year:
        filters["academic_year"] = up_to_year

    rows = frappe.get_all(
        "Assessment Result",
        filters=filters,
        fields=["course", "total_score", "academic_term", "program"],
    )
    rows = [
        r
        for r in rows
        if r.total_score not in (None, "")
        and (not program or not r.program or r.program == program)
    ]
    entries = []
    for r in rows:
        entries.append(
            {
                "course":        r.course,
                "units":         _get_course_units(r.course),
                "score":         r.total_score,
                "academic_term": r.academic_term,
            }
        )
    for eq in get_equivalence_entries(student):
        entries.append(
            {
                "course":        eq["course"],
                "units":         float(eq["units"] or 0),
                "score":         float(eq["grade"] or 0),
                "academic_term": None,
            }
        )
    return entries


def _cumulative_average_up_to(student, program_name, academic_term=None):
    """المعدل التراكمي حتى نهاية فصل محدد (أو كل الفصول إذا كان None)،
    بمنطق الكشوف الرسمية: تُستبعد مواد الرسوب من التراكمي — م40."""
    entries = _result_entries(student, program_name)
    upper = academic_term or "9999-12-31"
    return aggregate_averages(entries, current_term=upper)["cumulative_average"]


# ============================================================
# § 2.6  عدد محاولات المادة
# ============================================================

def get_attempt_count(student, course_name):
    """
    عدد محاولات الطالب في المادة (من Student Attempt Log).
    """
    return frappe.db.count(
        "Student Attempt Log",
        filters={"student": student, "course": course_name},
    )


def _consecutive_failures(attempts):
    """عدد الرسوب المتتالي في نهاية سلسلة المحاولات (مرتبة تصاعدياً) — م37."""
    run = 0
    for a in attempts:
        run = 0 if a.passed else run + 1
    return run


def get_attempt_status(student, course_name):
    """
    ما الحكم على الطالب بعد آخر محاولة؟ — م37

    Returns:
        "متاح"          — يمكنه إعادة المادة.
        "تحتاج موافقة" — استنفد الحد العادي (3) ويحتاج قرار إدارة للمحاولة 4.
        "فصل"           — رسب في 4 محاولات متتالية → يُفصل.
        "ناجح"          — اجتاز المادة.
    """
    attempts = frappe.get_all(
        "Student Attempt Log",
        filters={"student": student, "course": course_name},
        fields=["attempt_number", "passed"],
        order_by="attempt_number asc",
    )
    if not attempts:
        return get_rules().attempt_status_available

    if attempts[-1].passed:
        return get_rules().attempt_status_passed

    rules = get_rules()
    total       = len(attempts)
    consecutive = _consecutive_failures(attempts)

    if consecutive >= rules.expulsion_attempt:
        return rules.attempt_status_expulsion
    if total >= rules.max_attempts:
        return rules.attempt_status_approval
    return rules.attempt_status_available


def record_attempt(student, program_name, course_name, academic_year, academic_term, score):
    """
    يُسجّل محاولة جديدة في Student Attempt Log.
    يُفحص الحد الأقصى قبل التسجيل.

    Returns: (doc_name, warning_message | None)
    """
    rules = get_rules()
    status = get_attempt_status(student, course_name)
    warning = None

    if status == rules.attempt_status_expulsion:
        frappe.throw(
            _("رسب الطالب في مادة «{0}» في المحاولة رقم {1} — يستوجب الفصل من المعهد وفق § 2.6.").format(
                course_name, rules.expulsion_attempt
            ),
            title=_("تجاوز عدد محاولات المادة"),
        )

    if status == rules.attempt_status_approval:
        warning = _(
            "تنبيه: هذه المحاولة رقم {0} للطالب في مادة «{1}» — تتطلب موافقة الإدارة (§ 2.6)."
        ).format(rules.max_attempts + 1, course_name)

    # رقم المحاولة = أعلى رقم مسجّل + 1 (يتجنّب التصادم عند وجود فجوات)
    last = frappe.get_all(
        "Student Attempt Log",
        filters={"student": student, "course": course_name},
        pluck="attempt_number",
        order_by="attempt_number desc",
        limit=1,
    )
    attempt_no = int(last[0] if last else 0) + 1
    passed     = (float(score or 0) >= rules.pass_score)

    attempt_type = "عادي"
    if attempt_no >= rules.expulsion_attempt:
        attempt_type = "استثنائي (موافقة إدارة)"

    doc = frappe.new_doc("Student Attempt Log")
    doc.student        = student
    doc.program        = program_name
    doc.course         = course_name
    doc.academic_year  = academic_year
    doc.academic_term  = academic_term
    doc.attempt_number = attempt_no
    doc.score          = score
    doc.passed         = 1 if passed else 0
    doc.attempt_type   = attempt_type
    doc.insert(ignore_permissions=True)

    return doc.name, warning


# ============================================================
# § 2.7  المعادلة في المعدل التراكمي
# ============================================================

def get_equivalence_entries(student):
    """
    يُعيد مواد المعادلة **المرحّلة** للطالب، مرة واحدة لكل مادة.

    إذا تكرر سجل المعادلة لنفس المادة تُؤخذ أعلى درجة، لأن المحرك
    التراكمي يجب ألا يضاعف وحدات المادة أو نقاطها.
    """
    rows = frappe.get_all(
        "Student Equivalence",
        filters={"student": student, "docstatus": 1},
        fields=["course", "grade"],
    )
    best = {}
    for r in rows:
        if not r.course or r.grade in (None, ""):
            continue
        grade = float(r.grade)
        if r.course not in best or grade > best[r.course]:
            best[r.course] = grade

    result = []
    for course, grade in sorted(best.items()):
        units = _get_course_units(course)
        result.append({"course": course, "grade": grade, "units": units})
    return result


def compute_cumulative_gpa(student, program_name, up_to_term=None, up_to_year=None):
    """
    § 2.7 — المعدل التراكمي الرسمي عبر المحرك الوحيد `aggregate_averages`.

    - النتائج المرحّلة فقط (docstatus=1).
    - أفضل محاولة **ناجحة** لكل مادة؛ مادة لم تُجتَز لا تدخل الوحدات/النقاط.
    - المعادلة المرحّلة تدخل مرة واحدة.

    Returns dict:
        {
            "total_units":       float,  # الوحدات المحتسبة في التراكمي
            "total_points":      float,
            "cumulative_average": float, # 0–100
            "accomplished_units": float,
        }
    """
    entries = _result_entries(student, program_name, up_to_year=up_to_year)
    agg = aggregate_averages(
        entries,
        current_term=up_to_term or "9999-12-31",
    )
    return {
        "total_units":        agg["cumulative_units"],
        "total_points":       agg["cumulative_points"],
        "cumulative_average": agg["cumulative_average"],
        "accomplished_units": agg["accomplished_units"],
    }


# ============================================================
# § 2.8 — احتساب المعدل الفصلي والتراكمي والحالة
# مطابق للكشوف الرسمية للمعهد: مواد الرسوب (<50) تُستبعد من التراكمي،
# الإعادة تُحتسب بأعلى درجة مرة واحدة، مواد المعادلة تدخل التراكمي § 2.7.
# ============================================================

GRADE_LABELS = [
    ("ممتاز", 85),
    ("جيد جداً", 75),
    ("جيد فقط", 65),
    ("مقبول", 50),
    ("ضعيف", 35),
    ("ضعيف جداً", 0),
]

CUM_ALERT_THRESHOLD = 55.0  # إنذار إذا قل المعدل التراكمي عن 55% — م36 (fallback)
VERY_WEAK_THRESHOLD = 35.0  # «ضعيف جداً» < 35% → إنذار — م34/م36-ب (fallback)

_M34_SCALE_NAME = "تقدير م34"  # سلّم مرجع لتقدير معدّل الفصل § 2.5
_m34_cache = None


def _m34_labels():
    """قائمة (التقدير، الحد الأدنى) من سجل Grading Scale «تقدير م34» — قابلة للتعديل من الواجهة."""
    global _m34_cache
    if _m34_cache is not None:
        return _m34_cache
    try:
        rows = frappe.get_all(
            "Grading Scale Interval",
            filters={"parent": _M34_SCALE_NAME, "parenttype": "Grading Scale"},
            fields=["grade_description", "threshold"],
            order_by="threshold desc",
        )
        if rows:
            _m34_cache = [(r.grade_description, float(r.threshold)) for r in rows]
            return _m34_cache
    except Exception:
        pass
    _m34_cache = list(GRADE_LABELS)
    return _m34_cache


def reset_grade_scale_cache():
    """إفراغ كاش سلّم م34 — تُستدعى بعد تعديل السجل من الواجهة."""
    global _m34_cache
    _m34_cache = None


def grade_label(score):
    """التقدير الرسمي للدرجة وفق سلّم م34 — يقرأ من سجل Grading Scale «تقدير م34» مع fallback."""
    score = float(score or 0)
    for label, threshold in _m34_labels():
        if score >= threshold:
            return label
    return "ضعيف جداً"


def status_for(semester_average, cumulative_average):
    """حالة الفصل وفق اللائحة:
    - «إنذار» إذا كان التقدير العام الفصلي «ضعيف جداً» (<35) — م36-ب
      (ويتحول إلى فصل إذا تكرر في فصلين متتاليين — م37).
    - «إعادة» إذا فشل الفصل (المعدل <50) دون بلوغ حد «ضعيف جداً».
    - «إنذار» إذا قل المعدل التراكمي عن 55% — م36-ج.
    - وإلا «طبيعي».
    """
    rules = get_rules()
    sem = float(semester_average or 0)
    cum = float(cumulative_average or 0)
    if sem < rules.very_weak_threshold:
        return rules.semester_status_alert
    if sem < rules.pass_score:
        return rules.semester_status_repeat
    if cum < rules.cum_alert_threshold:
        return rules.semester_status_alert
    return rules.semester_status_normal


def _term_rank(term, cache):
    """مفتاح ترتيب زمني للفصل.

    الأولوية لتاريخ بداية الفصل؛ وإذا غاب (أو كان الفصل غير موجود) يُشتق
    تاريخ تقريبي من اسم الفصل (آخر سنة + موسم الفصل) لتفادي ترتيب خاطئ."""
    if term not in cache:
        start = frappe.db.get_value("Academic Term", term, "term_start_date") if term else None
        if start:
            cache[term] = (str(start), "")
        else:
            name = str(term or "")
            years = re.findall(r"\d{4}", name)
            year = int(years[-1]) if years else 0
            _rules = get_rules()
            if "خريف" in name:
                month = _rules.fall_month
            elif "ربيع" in name:
                month = _rules.spring_month
            else:
                month = "01"
            cache[term] = (f"{year:04d}-{month}", name)
    return cache[term]


def aggregate_averages(entries, current_term):
    """
    دالة حسابية خالصة (قابلة للاختبار بدون قاعدة بيانات).

    entries: [{"course", "units", "score", "academic_term"}]
    العناصر بـ academic_term = None تُعامل كمواد معادلة (تراكمي فقط § 2.7).
    """
    cache = {}
    current_rank = _term_rank(current_term, cache)
    units_of, best_cum, sem_best = {}, {}, {}

    for e in entries:
        course = e["course"]
        score = float(e.get("score") or 0)
        units = float(e.get("units") or 0)
        units_of[course] = units
        term = e.get("academic_term")
        if not term or _term_rank(term, cache) <= current_rank:
            if course not in best_cum or score > best_cum[course]:
                best_cum[course] = score
        if term == current_term:
            if course not in sem_best or score > sem_best[course]:
                sem_best[course] = score

    sem_units = round(sum(units_of[c] for c in sem_best), 2)
    sem_points = round(sum(sem_best[c] * units_of[c] for c in sem_best), 2)
    _ps = get_rules().pass_score
    cum_units = round(sum(units_of[c] for c, s in best_cum.items() if s >= _ps), 2)
    cum_points = round(sum(s * units_of[c] for c, s in best_cum.items() if s >= _ps), 2)
    sem_avg = round(sem_points / sem_units, 2) if sem_units else 0.0
    cum_avg = round(cum_points / cum_units, 2) if cum_units else 0.0

    return {
        "semester_units": sem_units,
        "semester_points": sem_points,
        "semester_average": sem_avg,
        "cumulative_units": cum_units,
        "cumulative_points": cum_points,
        "cumulative_average": cum_avg,
        "accomplished_units": cum_units,
        "status": status_for(sem_avg, cum_avg),
    }


def compute_semester_result(student, academic_term, program=None):
    """
    يحتسب حقول Student Semester Result من نتائج الطالب الفعلية.
    يُعيد None إذا لا توجد نتائج مسجلة في هذا الفصل (تبقى القيم يدوية).
    """
    if not student or not academic_term:
        return None

    if not frappe.db.exists(
        "Assessment Result",
        {"student": student, "academic_term": academic_term, "docstatus": 1},
    ):
        return None

    entries = _result_entries(student, program)
    if not any(e["academic_term"] is not None for e in entries):
        return None

    result = aggregate_averages(entries, current_term=academic_term)
    if not result["semester_units"]:
        return None
    return result


def recompute_all_semester_results(confirm=False):
    """إعادة احتساب كل سجلات Student Semester Result بالمحرك الرسمي.

    confirm=False → معاينة فقط (بدون تعديل)؛ confirm=True → تحديث فعلي.
    تُستخدم بعد الاستيرادات أو عند تصحيح القواعد — مع أخذ نسخة احتياطية أولاً.
    """
    frappe.flags.in_import = True
    names = frappe.get_all("Student Semester Result", pluck="name", order_by="creation asc")
    changed = unchanged = skipped = 0
    for name in names:
        doc = frappe.get_doc("Student Semester Result", name)
        result = compute_semester_result(doc.student, doc.academic_term, doc.program)
        if not result:
            skipped += 1
            continue
        diff = {}
        for k, v in result.items():
            if k == "status":
                if doc.get(k) != v:
                    diff[k] = (doc.get(k), v)
            elif abs(float(doc.get(k) or 0) - float(v or 0)) > 0.001:
                diff[k] = (doc.get(k), v)
        if not diff:
            unchanged += 1
            continue
        if confirm:
            for k, v in result.items():
                doc.db_set(k, v, update_modified=False)
        changed += 1
    if confirm:
        frappe.db.commit()
    return {
        "total": len(names),
        "changed": changed,
        "unchanged": unchanged,
        "skipped_no_results": skipped,
        "confirm": confirm,
    }


# ============================================================
# مشروع التخرج والتخرج — م43/م44/م46/م48
# ============================================================

def is_project_course(course_name):
    """هل المقرر هو مشروع التخرج؟ (م46)."""
    name = str(course_name or "")
    return "مشروع التخرج" in name or name.startswith("مشروع تخرج")


def get_graduation_eligibility(student, program_name):
    """
    أهلية التخرج — م43/م44/م46/م48.

    الشروط:
      - اجتياز جميع مقررات الخطة الدراسية بنجاح (≥50).
      - النجاح في مشروع التخرج بنسبة ≥65% (م46).
      - معدل تراكمي ≥55% (م43/م44).

    Returns dict:
        {
            "eligible": bool,
            "cumulative_average": float,
            "min_cumulative": float,
            "missing_courses": [...],     المواد غير المجتازة
            "project_courses": [...],     مقررات مشروع التخرج في الخطة
            "project_failed": [...],      مشاريع دون 65%
            "project_pass_score": float,
        }
    """
    program_courses = frappe.get_all(
        "Program Course",
        filters={"parent": program_name, "parenttype": "Program"},
        pluck="course",
    )

    rules = get_rules()
    best = {}
    for r in frappe.get_all(
        "Assessment Result",
        filters={"student": student, "program": program_name, "docstatus": 1},
        fields=["course", "total_score"],
    ):
        sc = float(r.total_score or 0)
        if r.course not in best or sc > best[r.course]:
            best[r.course] = sc
    for eq in get_equivalence_entries(student):
        c, g = eq["course"], float(eq["grade"] or 0)
        if c not in best or g > best[c]:
            best[c] = g

    missing = [c for c in program_courses if best.get(c, 0) < rules.pass_score]
    projects = [c for c in program_courses if is_project_course(c)]
    project_failed = [c for c in projects if best.get(c, 0) < rules.project_pass_score]
    cum_avg = _cumulative_average_up_to(student, program_name)

    eligible = (not missing) and (not project_failed) and cum_avg >= rules.graduation_min_avg

    return {
        "eligible":           eligible,
        "cumulative_average": cum_avg,
        "min_cumulative":     rules.graduation_min_avg,
        "missing_courses":    missing,
        "project_courses":    projects,
        "project_failed":     project_failed,
        "project_pass_score": rules.project_pass_score,
    }


# ============================================================
# أداة: تقرير وضع الطالب الكامل
# ============================================================

def student_status_report(student, program_name):
    """
    تقرير سريع عن وضع الطالب يجمع:
    - المعدل التراكمي
    - المواد الراسبة والمحاولات
    - المواد التي استنفد محاولاتها
    - حالة وقف القيد إن وُجدت

    Returns: dict
    """
    gpa = compute_cumulative_gpa(student, program_name)

    # مواد الإنذار (محاولات متتالية فاشلة) — م36/م37
    attempt_logs = frappe.get_all(
        "Student Attempt Log",
        filters={"student": student, "program": program_name},
        fields=["course", "attempt_number", "passed"],
        order_by="course asc, attempt_number asc",
    )
    by_course = {}
    for log in attempt_logs:
        by_course.setdefault(log.course, []).append(log)

    warnings = []
    rules = get_rules()
    for course, logs in by_course.items():
        if logs[-1].passed:
            continue
        consecutive = _consecutive_failures(logs)
        if consecutive >= rules.expulsion_attempt:
            warnings.append({"course": course, "status": rules.attempt_status_expulsion, "attempts": consecutive})
        elif len(logs) >= rules.max_attempts:
            warnings.append({"course": course, "status": rules.attempt_status_approval, "attempts": len(logs)})
        elif consecutive >= rules.second_failure_warning:
            warnings.append({"course": course, "status": "إنذار (المرة الثانية)", "attempts": consecutive})

    # وقف القيد
    suspension = frappe.get_all(
        "Student Suspension",
        filters={"student": student, "status": rules.suspension_status},
        fields=["suspended_term", "suspended_year"],
        limit=1,
    )

    return {
        "student":              student,
        "program":              program_name,
        "gpa":                  gpa,
        "attempt_warnings":     warnings,
        "active_suspension":    suspension[0] if suspension else None,
    }


# ============================================================
# دالة ترحيل: بناء Student Attempt Log من Assessment Results
# ============================================================

def build_attempt_log_from_history():
    """
    يبني سجلات Student Attempt Log من الـ Assessment Results الموجودة.
    يُشغَّل مرة واحدة بعد اكتمال ترحيل الدرجات.

    الخوارزمية:
    - لكل طالب × مادة: يرتب النتائج زمنياً ويُعدّد المحاولات بالترتيب.
    """
    frappe.flags.in_import = True

    results = frappe.get_all(
        "Assessment Result",
        filters={"docstatus": 1},
        fields=["student", "program", "course", "total_score", "academic_year", "academic_term"],
        order_by="student asc, course asc, academic_year asc, academic_term asc",
    )

    # تجميع: (student, course) → [(ay, term, score), ...]
    from collections import defaultdict
    buckets = defaultdict(list)
    for r in results:
        buckets[(r.student, r.course)].append(
            (r.academic_year, r.academic_term, r.total_score, r.program)
        )

    created = skipped = 0
    rules = get_rules()
    for (student, course), entries in buckets.items():
        for attempt_no, (ay, term, score, program) in enumerate(entries, start=1):
            exists = frappe.db.exists(
                "Student Attempt Log",
                {"student": student, "course": course, "attempt_number": attempt_no},
            )
            if exists:
                skipped += 1
                continue

            passed = 1 if float(score or 0) >= rules.pass_score else 0
            attempt_type = "عادي"
            if attempt_no >= rules.expulsion_attempt:
                attempt_type = "استثنائي (موافقة إدارة)"

            doc = frappe.new_doc("Student Attempt Log")
            doc.student        = student
            doc.program        = program
            doc.course         = course
            doc.academic_year  = ay
            doc.academic_term  = term
            doc.attempt_number = attempt_no
            doc.score          = score
            doc.passed         = passed
            doc.attempt_type   = attempt_type
            doc.insert(ignore_permissions=True)
            created += 1
            if created % 100 == 0:
                frappe.db.commit()

    frappe.db.commit()
    print(
        "Student Attempt Log → created:", created,
        "| skipped:", skipped,
        "| total:", frappe.db.count("Student Attempt Log"),
    )
    return {"created": created, "skipped": skipped}
