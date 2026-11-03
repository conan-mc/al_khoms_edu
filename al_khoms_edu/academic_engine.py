# -*- coding: utf-8 -*-
"""
Wrapper for academic_rules.py to maintain backward compatibility with hooks.
"""

import frappe
from frappe import _
from al_khoms_edu import academic_rules as ar

def after_assessment_submit(doc, method=None):
    """يُسجَّل المحاولة فقط عند اعتماد النتيجة (docstatus=1).

    المسودات لا تُنشئ Student Attempt Log مطلقاً. أثناء الترحيل التاريخي
    تُبنى المحاولات من سجل النتائج المرحّلة عبر build_attempt_log_from_history.
    """
    if getattr(frappe.flags, "in_import", False):
        return
    if doc.docstatus != 1:
        return
    _handle_assessment_result(doc)


def _handle_assessment_result(doc):
    """Core logic for handling a submitted Assessment Result."""
    student = doc.student
    course = doc.course
    score = doc.total_score or 0
    program = doc.get("program") or ar.get_student_program(student)
    if not program:
        # If no program, we cannot record attempt properly; just return
        return
    # Record the attempt (this will create a Student Attempt Log entry).
    # إذا رمزت record_attempt (مثل حالة الفصل) يُترك الاستثناء ينتشر للمستخدم.
    doc_name, warning = ar.record_attempt(
        student=student,
        program_name=program,
        course_name=course,
        academic_year=doc.academic_year,
        academic_term=doc.academic_term,
        score=score,
    )
    if warning:
        frappe.msgprint(warning, title=_("تنبيه المحاولات"), indicator="orange", alert=True)

def before_course_enrollment_save(doc, method=None):
    """Hook before saving a Course Enrollment.
    It enforces suspension, prerequisite checking and the optional *full score entry* rule.
    """
    student = doc.student
    course = doc.course

    # الترحيل التاريخي: البيانات القديمة سابقة لقاعدة المتطلبات — تُستورد كما هي
    if frappe.flags.get("skip_prerequisite_check"):
        return

    # § 2.5 — الطالب الموقوف لا يُسجَّل في مقررات جديدة (يُسمح بتعديل السجلات القائمة)
    if doc.is_new():
        suspension_error = get_suspension_message(student)
        if suspension_error:
            frappe.throw(suspension_error, title=_("الطالب موقوف القيد"))

    # Prerequisite check – reuse check_prerequisites_met
    # (على السجلات الجديدة فقط — لا يمنع تعديل تسجيلات قائمة من بيانات سابقة)
    if not doc.is_new():
        return

    # Get the explicit program or the student's latest program
    program = doc.get("program") or ar.get_student_program(student)
    if program:
        met, missing = ar.check_prerequisites_met(student, program, course)
        if not met:
            frappe.throw(
                _("لا يمكن تسجيل الطالب في مادة «{0}» قبل النجاح في المواد المتطلبة التالية:<br>{1}").format(
                    course, _missing_courses_html(missing)
                ),
                title=_("متطلبات سابقة غير مكتملة"),
            )


def _missing_courses_html(courses):
    """يعرض المواد الناقصة كقائمة واضحة."""
    return "<br>".join(f"• {course}" for course in courses)


def get_suspension_message(student):
    """§ 2.5 — يُعيد رسالة عربية إن كان الطالب موقوف القيد، وإلا None."""
    if not student:
        return None

    info = frappe.db.get_value(
        "Student", student, ["name", "student_name", "is_suspended"], as_dict=True
    )
    if not info or not info.is_suspended:
        return None

    suspension = frappe.db.get_value(
        "Student Suspension",
        {"student": student, "status": ar.get_rules().suspension_status},
        ["suspended_term", "suspended_year"],
        as_dict=True,
    )
    details = ""
    if suspension and (suspension.suspended_term or suspension.suspended_year):
        details = _(" — الفصل: {0} / السنة: {1}").format(
            suspension.suspended_term or "—", suspension.suspended_year or "—"
        )

    return _("لا يمكن تسجيل مقررات جديدة للطالب {0}: قيده موقوف{1}. لا يُرفع الوقف إلا بقرار رسمي.").format(
        info.student_name or student, details
    )


def get_student_program(student):
    """يجلب البرنامج المسجل به الطالب من المحرك الوحيد."""
    return ar.get_student_program(student)


def can_enroll(student, course, academic_year, term):
    """يتحقق مما إذا كان الطالب مؤهلاً للتسجيل في مادة معينة.
    القاعدة: لا يُسجَّل الطالب الموقوف، ولا يجتاز مادة قبل النجاح في سابقتها.
    """
    # § 2.5 — وقف القيد قبل أي فحص آخر (حتى المستثنى)
    suspension_error = get_suspension_message(student)
    if suspension_error:
        return False, suspension_error

    program = get_student_program(student)
    if not program:
        return True, "لا يوجد برنامج مسجل للطالب"

    # Uses the same engine as assessment validation (and honours Student.exempt)
    met, missing = ar.check_prerequisites_met(student, program, course)
    if not met:
        return False, _("يجب النجاح في المواد المتطلبة التالية أولاً:<br>{0}").format(
            _missing_courses_html(missing)
        )
    return True, _("تم اجتياز المتطلبات السابقة")

def get_attempt_count(student, course):
    """يحسب عدد محاولات الرسوب في مادة معينة.
    القاعدة: كل نتيجة < 50 تعتبر محاولة رسوب.
    """
    # Use academic_rules which counts from Student Attempt Log
    return ar.get_attempt_count(student, course)

def evaluate_promotion(student, academic_year, academic_term):
    """يحدد حالة الطالب في نهاية الفصل الدراسي.
    القاعدة:
    - 0 راسب: ينتقل للفصل الأعلى.
    - 1 أو 2 راسب: ينتقل للأعلى مع ترحيل المواد الراسبة.
    - 3 فأكثر: يعيد الفصل (المواد الراسبة فقط).
    """
    # Get program from latest enrollment
    prog = frappe.get_all(
        "Program Enrollment",
        filters={"student": student},
        fields=["program"],
        order_by="creation desc",
        limit=1,
    )
    program = prog[0].program if prog else None
    if not program:
        return "Unknown", "لا يوجد برنامج مسجل للطالب"
    # Use academic_rules to get promotion decision
    result = ar.get_promotion_decision(student, program, academic_year, academic_term)
    decision = result["decision"]
    # Map decision to expected strings
    map_dec = {
        "ترقية": "Promoted",
        "ترقية مع ترحيل": "Promoted with Carry-over",
        "إعادة فصل": "Repeat Semester",
    }
    return map_dec.get(decision, decision), decision

def weekly_promotion_evaluation():
    """Scheduled task – runs once a week.
    It iterates over all students, evaluates their promotion status for the latest
    academic term and updates the `promotion_status` field on the Student doc.
    """
    if not frappe.db.has_column("Student", "promotion_status"):
        # الحقل غير موجود بعد (لم يُنفَّذ seed/migrate)
        return

    ar.reset_units_cache()

    latest = {}
    for row in frappe.db.sql(
        """
        SELECT t.student, t.academic_year, t.academic_term
        FROM `tabAssessment Result` t
        JOIN (
            SELECT student, MAX(creation) AS mc
            FROM `tabAssessment Result`
            WHERE docstatus = 1
            GROUP BY student
        ) latest ON latest.student = t.student AND latest.mc = t.creation
        WHERE t.docstatus = 1
        """,
        as_dict=True,
    ):
        latest[row.student] = (row.academic_year, row.academic_term)

    for student, (ay, term) in latest.items():
        # Get program
        program = get_student_program(student)
        if not program:
            continue
        decision = ar.get_promotion_decision(student, program, ay, term)["decision"]
        # Update student doc without triggering full save/validations
        frappe.db.set_value("Student", student, "promotion_status", decision, update_modified=False)
    frappe.db.commit()
    print(f"تم تقييم الترقية لـ {len(latest)} طالباً.")