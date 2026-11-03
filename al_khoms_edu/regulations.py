# -*- coding: utf-8 -*-
"""محرّك اللائحة الداخلية لمعاهد التقنية العليا.

يُنفّذ:
1. رقم القيد الموحّد (مادة 13): 9 خانات.
2. توزيع الدرجات (المواد 20، 21، 32): 25+15+40+20.
3. شرط اجتياز العملي قبل النظري النهائي (مادة 20).
4. الحرمان بالغياب (مادة 22): > 25% نظري أو جلستان عمليتان.
5. منع التسجيل أثناء العقوبة التأديبية (المواد 51–72).

كل الدوال هنا تُسجَّل عبر hooks.py، ولا تُستدعى يدوياً.
"""

import re

import frappe
from frappe import _
from frappe.utils import getdate

from al_khoms_edu import academic_rules as ar

# ----------------------------------------------------------------------
# ثوابت اللائحة
# ----------------------------------------------------------------------

ADMIN_CODE = "2"          # خانة إدارة المعاهد العليا
INSTITUTE_CODE = "37"     # خانتا رقم المعهد

UNIFIED_RE = re.compile(r"^\d{9}$")

THEORY_WORK_MAX = 25.0
PRACTICAL_WORK_MAX = 15.0
THEORY_FINAL_MAX = 40.0
PRACTICAL_FINAL_MAX = 20.0

PRACTICAL_MAX = PRACTICAL_WORK_MAX + PRACTICAL_FINAL_MAX   # 35
PRACTICAL_PASS = PRACTICAL_MAX / 2.0                       # 17.5

ABSENCE_LIMIT = 25.0
PRACTICAL_ABSENCE_LIMIT = 2
MAX_TOTAL_SCORE = 100.0

FAIL_GRADES = ("F", "راسب")

COMPONENTS = (
	("theory_work_score", THEORY_WORK_MAX),
	("practical_work_score", PRACTICAL_WORK_MAX),
	("theory_final_score", THEORY_FINAL_MAX),
	("practical_final_score", PRACTICAL_FINAL_MAX),
)

GRADE_INTERVALS = [
	("راسب", 0),
	("مقبول", 50),
	("جيد", 65),
	("جيد جداً", 75),
	("ممتاز", 85),
]

_DIGIT_MAP = {ord(ch): str(i) for i, ch in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(ch): str(i) for i, ch in enumerate("۰۱۲۳۴۵۶۷۸۹")})


def _digits(value):
	return str(value or "").translate(_DIGIT_MAP).strip()


def _grade_for(score):
	score = float(score or 0)
	for name, threshold in reversed(GRADE_INTERVALS):
		if score >= threshold:
			return name
	return "راسب"


def _has_field(doctype, fieldname):
	return frappe.get_meta(doctype).has_field(fieldname)


def _bypass():
	"""تخطّي التحقق أثناء الترحيل التاريخي أو الاستيراد."""
	return bool(
		getattr(frappe.flags, "in_import", False)
		or getattr(frappe.flags, "in_migrate", False)
		or getattr(frappe.flags, "in_disciplinary_action", False)
	)


# ----------------------------------------------------------------------
# 1) رقم القيد الموحّد — مادة 13
# ----------------------------------------------------------------------

def build_unified_number(student):
	"""يُولّد رقم قيد من 9 خانات: إدارة(1) + معهد(2) + سنة(2) + فصل(1) + تسلسل(3)."""
	year, term_no = _enrollment_year_term(student)
	prefix = f"{ADMIN_CODE}{INSTITUTE_CODE}{year % 100:02d}{term_no}"
	serial = _next_serial(prefix)
	return f"{prefix}{serial:03d}"


def _next_serial(prefix):
	rows = frappe.db.sql(
		"select unified_registration_no from `tabStudent` "
		"where unified_registration_no like %s",
		(prefix + "%",),
	)
	used = set()
	for (value,) in rows:
		tail = _digits(value)[len(prefix):]
		if tail.isdigit():
			used.add(int(tail))
	serial = 1
	while serial in used:
		serial += 1
	if serial > 999:
		frappe.throw(
			_("استُنفدت الأرقام التسلسلية للبادئة {0} (999 رقمًا).").format(prefix),
			title=_("رقم القيد الموحد"),
		)
	return serial


def _enrollment_year_term(student):
	"""سنة وفصل الالتحاق من آخر تسجيل برنامج، وإلا من تاريخ الالتحاق."""
	name = student.get("name")
	if name:
		row = frappe.get_all(
			"Program Enrollment",
			filters={"student": name},
			fields=["academic_year", "academic_term"],
			order_by="creation asc",
			limit=1,
		)
		if row:
			year = _parse_year(row[0].academic_year)
			term = _parse_term(row[0].academic_term)
			if year:
				return year, term

	joining = student.get("joining_date")
	if joining:
		date = getdate(joining)
	else:
		date = getdate()
	term_no = 1 if date.month >= 8 else 2
	return date.year, term_no


def _parse_year(value):
	years = re.findall(r"\d{4}", str(value or ""))
	if not years:
		return None
	return int(years[0])


def _parse_term(value):
	text = str(value or "")
	if "ربيع" in text:
		return 2
	return 1


def validate_student(doc, method=None):
	"""يتحقق من الرقم الموحد ويُولّده للطلاب الجدد."""
	if _bypass():
		return

	if doc.is_new() and _has_field("Student", "mother_name") and not doc.get("mother_name"):
		frappe.throw(
			_("اسم الأم إجباري عند تسجيل طالب جديد."),
			title=_("بيانات ناقصة"),
		)

	value = _digits(doc.get("unified_registration_no"))

	if not value:
		if doc.is_new():
			doc.unified_registration_no = build_unified_number(doc)
		return

	if not UNIFIED_RE.match(value):
		frappe.throw(
			_(
				"رقم القيد الموحّد يجب أن يتكوّن من 9 أرقام: "
				"إدارة (1) + معهد (2) + سنة الالتحاق (2) + الفصل (1) + التسلسل (3)."
				"<br>القيمة المُدخلة: «{0}»"
			).format(value),
			title=_("رقم قيد غير صحيح"),
		)

	duplicate = frappe.db.get_value(
		"Student",
		{"unified_registration_no": value, "name": ["!=", doc.name]},
		["name", "student_name"],
		as_dict=True,
	)
	if duplicate:
		frappe.throw(
			_("رقم القيد {0} مسجّل للطالب {1} ({2}).").format(
				value, duplicate.student_name or "", duplicate.name
			),
			title=_("رقم قيد مكرر"),
		)

	doc.unified_registration_no = value


# ----------------------------------------------------------------------
# 2) الغياب والحرمان — مادة 22
# ----------------------------------------------------------------------

def validate_course_enrollment(doc, method=None):
	"""يحسب الحرمان من الغياب عند حفظ تسجيل المادة."""
	if _bypass() or not _has_field("Course Enrollment", "absence_percent"):
		return

	percent = float(doc.get("absence_percent") or 0)
	practical = int(doc.get("practical_absences") or 0)

	reasons = []
	if percent > ABSENCE_LIMIT:
		reasons.append(
			_("تجاوز الغياب النظري {0}% (الحد {1}%)").format(percent, int(ABSENCE_LIMIT))
		)
	if practical >= PRACTICAL_ABSENCE_LIMIT:
		reasons.append(
			_("الغياب عن {0} جلسات عملية (الحد جلستان)").format(practical)
		)

	if reasons:
		doc.is_deprived = 1
		doc.deprivation_reason = " — ".join(reasons) + " (مادة 22)"
	else:
		doc.is_deprived = 0
		doc.deprivation_reason = ""


# ----------------------------------------------------------------------
# 3) توزيع الدرجات وشرط العملي — المواد 20، 21، 32
# ----------------------------------------------------------------------

def prepare_assessment_result(doc, method=None):
	"""يُكمل السنة/الفصل/البرنامج من خطة التقييم أو مجموعة الطلاب.

	يُسجَّل في before_validate حتى تكتمل القيم قبل فحص الحقول الإجبارية،
	ويُتاح تجاوز الاستيراد التاريخي المسجَّل في `_bypass()`.
	"""
	if _bypass():
		if not doc.get("academic_term"):
			doc.flags.ignore_mandatory = True
		return

	if not doc.get("assessment_plan"):
		return

	plan = frappe.db.get_value(
		"Assessment Plan",
		doc.assessment_plan,
		["program", "course", "academic_year", "academic_term", "student_group"],
		as_dict=True,
	)
	if not plan:
		return

	for field in ("program", "course", "academic_year", "academic_term", "student_group"):
		if not doc.get(field) and plan.get(field):
			doc.set(field, plan.get(field))

	if not doc.get("student_group") and plan.get("student_group"):
		doc.student_group = plan.get("student_group")

	if doc.get("student_group") and not doc.get("academic_term"):
		group_term = frappe.db.get_value(
			"Student Group", doc.student_group, "academic_term"
		)
		if group_term:
			doc.academic_term = group_term

	if not doc.get("academic_year") and doc.get("academic_term"):
		doc.academic_year = frappe.db.get_value(
			"Academic Term", doc.academic_term, "academic_year"
		)

	if not doc.get("program"):
		doc.program = ar.get_student_program(doc.student)

	if not doc.get("academic_term"):
		frappe.throw(
			_(
				"الفصل الأكاديمي إجباري على نتيجة التقييم. "
				"حدّده في خطة التقييم أو مجموعة الطلاب أو في السجل نفسه."
			),
			title=_("فصل أكاديمي مفقود"),
		)


def _validate_term_year(doc, label="السجل"):
	"""يتأكد أن الفصل مرتبط بالسنة الأكاديمية المختارة نفسها."""
	if _bypass() or not doc.get("academic_term") or not doc.get("academic_year"):
		return

	term_year = frappe.db.get_value(
		"Academic Term", doc.academic_term, "academic_year"
	)
	if term_year and term_year != doc.academic_year:
		frappe.throw(
			_(
				"{0}: الفصل «{1}» يتبع السنة «{2}»، لا السنة المختارة «{3}»."
			).format(label, doc.academic_term, term_year, doc.academic_year),
			title=_("تعارض السنة والفصل"),
		)


def validate_assessment_result(doc, method=None):
	if _bypass() or not _has_field("Assessment Result", "theory_work_score"):
		return

	_validate_term_year(doc, _("نتيجة التقييم"))

	# سقف 100 درجة — يُطبَّق على الإدخال المباشر أيضاً وليس المكوّنات فقط
	has_components = any(
		doc.get(field) not in (None, "") for field, _maximum in COMPONENTS
	)
	if not has_components and float(doc.get("total_score") or 0) > MAX_TOTAL_SCORE:
		frappe.throw(
			_(
				"الدرجة الإجمالية للمقرر لا يمكن أن تتجاوز 100 درجة "
				"بحسب اللائحة الأكاديمية المعتمدة."
			),
			title=_("خطأ في إدخال الدرجات"),
		)

	_check_prerequisites(doc)

	entered = {
		field: doc.get(field)
		for field, _maximum in COMPONENTS
		if doc.get(field) not in (None, "")
	}
	if not entered:
		return

	for field, maximum in COMPONENTS:
		value = doc.get(field)
		if value in (None, ""):
			doc.set(field, 0)
			continue
		value = float(value)
		if value < 0:
			frappe.throw(_("الدرجة لا يمكن أن تكون سالبة: {0}").format(field))
		if value > maximum:
			frappe.throw(
				_("الدرجة {0} تتجاوز الحد الأقصى {1} للمكوّن {2}.").format(
					value, maximum, _(field)
				),
				title=_("درجة غير صحيحة"),
			)

	practical_total = float(doc.get("practical_work_score") or 0) + float(
		doc.get("practical_final_score") or 0
	)
	doc.practical_total = practical_total

	has_practical = _course_has_practical(doc.course)
	if (
		has_practical
		and float(doc.get("theory_final_score") or 0) > 0
		and practical_total < PRACTICAL_PASS
	):
		frappe.throw(
			_(
				"لا يحق للطالب التقدّم للامتحان النهائي النظري: "
				"درجته في الجزء العملي {0} من {1} (الحد الأدنى {2})."
			).format(practical_total, PRACTICAL_MAX, PRACTICAL_PASS),
			title=_("لم يجتز الجزء العملي — مادة 20"),
		)

	absence = _absence_for(doc)
	if absence and _is_deprived(absence):
		doc.is_deprived = 1
		doc.deprivation_reason = _deprivation_reason(absence)
		doc.total_score = 0
		doc.grade = "راسب"
		frappe.msgprint(
			_("الطالب محروم من هذا المقرر (مادة 22) — رُصدت له درجة صفر."),
			alert=True,
			indicator="red",
		)
		return

	doc.is_deprived = 0
	doc.deprivation_reason = ""

	total = sum(float(doc.get(field) or 0) for field, _maximum in COMPONENTS)
	doc.maximum_score = 100
	doc.total_score = total
	doc.course_work_score = float(doc.get("theory_work_score") or 0) + float(
		doc.get("practical_work_score") or 0
	)
	doc.final_exam_score = float(doc.get("theory_final_score") or 0) + float(
		doc.get("practical_final_score") or 0
	)
	doc.grade = _grade_for(total)


def _check_prerequisites(doc):
	"""يمنع تقييد درجة مقرر لم تُجتَز متطلباته السابقة.

	يستخدم **نفس** دالة التسجيل: Course Prerequisite + Program Prerequisite،
	ونفس قاعدة النجاح (نتائج مرحّلة + معادلات مرحّلة).
	"""
	if not doc.student or not doc.course:
		return

	program = doc.get("program") or ar.get_student_program(doc.student)
	met, missing = ar.check_prerequisites_met(doc.student, program, doc.course)
	if not met:
		frappe.throw(
			_(
				"لا يمكن تقييد درجة المادة «{0}» لأن الطالب لم يجتز المتطلب السابق المعتمد: {1}"
			).format(doc.course, "، ".join(missing)),
			title=_("خرق نظام الاعتمادية الأكاديمية"),
		)


def _has_passed(student, course):
	"""غلاف توافقي: النجاح المعتمد من المحرك الوحيد فقط."""
	return ar.has_passed_course(student, course)


def _course_has_practical(course):
	if not course:
		return False
	hours = frappe.db.get_value("Course", course, "practical_hours")
	return bool(hours and float(hours) > 0)


def _absence_for(doc):
	"""يجلب تسجيل المادة المطابق للسنة والفصل، وإلا الأحدث."""
	if not doc.student or not doc.course:
		return None
	rows = frappe.db.sql(
		"""
		select ce.name, ce.absence_percent, ce.practical_absences
		from `tabCourse Enrollment` ce
		left join `tabProgram Enrollment` pe on pe.name = ce.program_enrollment
		where ce.student = %s and ce.course = %s
		order by
			case when pe.academic_year = %s and pe.academic_term = %s then 0 else 1 end,
			ce.creation desc
		limit 1
		""",
		(doc.student, doc.course, doc.academic_year, doc.academic_term),
		as_dict=True,
	)
	return rows[0] if rows else None


def _is_deprived(row):
	return bool(
		float(row.get("absence_percent") or 0) > ABSENCE_LIMIT
		or int(row.get("practical_absences") or 0) >= PRACTICAL_ABSENCE_LIMIT
	)


def _deprivation_reason(row):
	if float(row.get("absence_percent") or 0) > ABSENCE_LIMIT:
		return _("الغياب النظري يتجاوز 25% — مادة 22")
	return _("الغياب عن جلستين عمليتين — مادة 22")


# ----------------------------------------------------------------------
# 4) منع التسجيل أثناء العقوبة — المواد 51–72
# ----------------------------------------------------------------------

def validate_program_enrollment(doc, method=None):
	if _bypass():
		if not doc.get("academic_term"):
			doc.flags.ignore_mandatory = True
		return

	from al_khoms_edu.academic_engine import get_suspension_message

	message = get_suspension_message(doc.student)
	if message:
		frappe.throw(message, title=_("الطالب موقوف القيد"))

	status = frappe.db.get_value("Student", doc.student, "disciplinary_status")
	if status == "مفصول":
		frappe.throw(
			_("لا يمكن تسجيل الطالب {0}: صدر بحقه قرار فصل نهائي.").format(doc.student),
			title=_("فصل نهائي"),
		)

	if not doc.get("academic_term"):
		frappe.throw(
			_(
				"الفصل الأكاديمي إجباري على تسجيل البرنامج. "
				"اختر الفصل قبل الحفظ أو الاعتماد."
			),
			title=_("فصل أكاديمي مفقود"),
		)

	_validate_term_year(doc, _("تسجيل البرنامج"))

	# قاعدة الثلاث مواد قرار نهاية فصل، لا بوابة تمنع التسجيل.
	# عند وجود قرار «إعادة فصل» يُقيَّد التسجيل الجديد بالمواد الراسبة فقط.
	ar.prepare_repeat_term_courses(doc)


# ----------------------------------------------------------------------
# 5) تركيب الحقول المخصصة
# ----------------------------------------------------------------------

STUDENT_FIELDS = [
	{
		"fieldname": "mother_name",
		"label": "اسم الأم",
		"fieldtype": "Data",
		"insert_after": "student_name",
		"description": "اختياري حالياً — لا يُفرض على السجلات القائمة",
	},
	{
		"fieldname": "unified_registration_no",
		"label": "رقم القيد الموحد",
		"fieldtype": "Data",
		"insert_after": "legacy_student_number",
		"unique": 1,
		"in_list_view": 1,
		"description": "9 أرقام: إدارة (1) + معهد (2) + سنة (2) + فصل (1) + تسلسل (3) — مادة 13",
	},
	{
		"fieldname": "disciplinary_status",
		"label": "الحالة التأديبية",
		"fieldtype": "Select",
		"options": "سليم\nإنذار\nموقوف\nمفصول",
		"default": "سليم",
		"insert_after": "unified_registration_no",
		"read_only": 1,
		"in_list_view": 1,
	},
]

COURSE_FIELDS = [
	{
		"fieldname": "alternative_course_codes",
		"label": "رموز المقرر الإضافية",
		"fieldtype": "Small Text",
		"insert_after": "course_code",
		"description": "رموز مترادفة أو اعتماد دولي — منفصلة بفاصلة",
	},
	{
		"fieldname": "custom_credits",
		"label": "عدد الوحدات (custom_credits)",
		"fieldtype": "Int",
		"insert_after": "units",
		"default": "0",
		"description": "مرآة اختيارية لحقل units — للتوافق مع البرومبت المرجعي",
	},
	{
		"fieldname": "custom_points",
		"label": "عدد النقاط (custom_points)",
		"fieldtype": "Float",
		"insert_after": "custom_credits",
		"default": "0",
	},
	{
		"fieldname": "pre_requisite_courses",
		"label": "المتطلبات السابقة (الاعتمادية)",
		"fieldtype": "Table MultiSelect",
		"options": "Course Prerequisite",
		"insert_after": "custom_points",
		"description": "يمنع تقييد درجة المادة قبل اجتياز هذه المواد",
	},
]

COURSE_ENROLLMENT_FIELDS = [
	{
		"fieldname": "full_score_entry",
		"label": "دخول 100%",
		"fieldtype": "Check",
		"insert_after": "course",
	},
	{
		"fieldname": "absence_percent",
		"label": "نسبة الغياب النظري %",
		"fieldtype": "Float",
		"insert_after": "course",
		"default": "0",
		"description": "الحرمان عند تجاوز 25% — مادة 22",
	},
	{
		"fieldname": "practical_absences",
		"label": "عدد جلسات الغياب العملي",
		"fieldtype": "Int",
		"insert_after": "absence_percent",
		"default": "0",
		"description": "الحرمان عند بلوغ جلستين — مادة 22",
	},
	{
		"fieldname": "is_deprived",
		"label": "محروم من الامتحان",
		"fieldtype": "Check",
		"insert_after": "practical_absences",
		"read_only": 1,
	},
	{
		"fieldname": "deprivation_reason",
		"label": "سبب الحرمان",
		"fieldtype": "Small Text",
		"insert_after": "is_deprived",
		"read_only": 1,
	},
]

ASSESSMENT_RESULT_FIELDS = [
	{
		"fieldname": "course_work_score",
		"label": "درجة أعمال الفصل",
		"fieldtype": "Float",
		"insert_after": "total_score",
	},
	{
		"fieldname": "final_exam_score",
		"label": "درجة الامتحان النهائي",
		"fieldtype": "Float",
		"insert_after": "course_work_score",
	},
	{
		"fieldname": "theory_work_score",
		"label": "أعمال الفصل — نظري (25)",
		"fieldtype": "Float",
		"insert_after": "final_exam_score",
	},
	{
		"fieldname": "practical_work_score",
		"label": "أعمال الفصل — عملي (15)",
		"fieldtype": "Float",
		"insert_after": "theory_work_score",
	},
	{
		"fieldname": "theory_final_score",
		"label": "النهائي — نظري (40)",
		"fieldtype": "Float",
		"insert_after": "practical_work_score",
	},
	{
		"fieldname": "practical_final_score",
		"label": "النهائي — عملي (20)",
		"fieldtype": "Float",
		"insert_after": "theory_final_score",
	},
	{
		"fieldname": "practical_total",
		"label": "مجموع العملي (35)",
		"fieldtype": "Float",
		"insert_after": "practical_final_score",
		"read_only": 1,
	},
	{
		"fieldname": "is_deprived",
		"label": "محروم من الامتحان",
		"fieldtype": "Check",
		"insert_after": "practical_total",
		"read_only": 1,
	},
	{
		"fieldname": "deprivation_reason",
		"label": "سبب الحرمان",
		"fieldtype": "Small Text",
		"insert_after": "is_deprived",
		"read_only": 1,
	},
]


def install_custom_fields():
	"""يُنشئ الحقول المخصصة (idempotent)."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	created = 0
	for doctype, fields in (
		("Student", STUDENT_FIELDS),
		("Course", COURSE_FIELDS),
		("Course Enrollment", COURSE_ENROLLMENT_FIELDS),
		("Assessment Result", ASSESSMENT_RESULT_FIELDS),
	):
		for definition in fields:
			if frappe.db.exists(
				"Custom Field",
				{"dt": doctype, "fieldname": definition["fieldname"]},
			):
				continue
			create_custom_field(doctype, definition, ignore_validate=True)
			created += 1

	if created:
		frappe.clear_cache()
	frappe.db.commit()
	return created


def _ensure_required_property(doctype, fieldname):
	"""يجعل الحقل إجبارياً في الواجهة دون تعديل ملف DocType الأصلي."""
	if not frappe.get_meta(doctype).has_field(fieldname):
		return False

	from frappe.custom.doctype.property_setter.property_setter import (
		make_property_setter,
	)

	filters = {
		"doc_type": doctype,
		"field_name": fieldname,
		"property": "reqd",
	}
	existing = frappe.db.get_value("Property Setter", filters, "name")
	if existing:
		if str(frappe.db.get_value("Property Setter", existing, "value")) != "1":
			frappe.db.set_value("Property Setter", existing, "value", "1")
			frappe.clear_cache(doctype=doctype)
		return False

	make_property_setter(doctype, fieldname, "reqd", "1", "Check")
	frappe.clear_cache(doctype=doctype)
	return True


def apply_phase1_setup():
	"""يطبّق سياسة Phase 1: الفصل الإجباري + فصل صلاحيات الاعتماد.

	آمن للاستدعاء المتكرر. لا يُنشئ بيانات أكاديمية ولا يمسّ النتائج.
	"""
	from al_khoms_edu.permissions import apply_academic_permissions

	created = 0
	for doctype in ("Assessment Result", "Program Enrollment"):
		if _ensure_required_property(doctype, "academic_term"):
			created += 1

	frappe.db.set_single_value("Education Settings", "academic_term_reqd", 1)
	frappe.clear_cache()
	permissions = apply_academic_permissions()
	return {
		"required_fields_created": created,
		"permissions": permissions,
	}


def _install_seed_custom_fields():
	"""حقول `seed.CUSTOM_FIELDS` لا تعتمد على وجود شركة.

	`seed.run()` (patch `run_seed`) يتخطى بالكامل عند غياب شركة، فتضيع حقول
	Course / Program Course / Program / Student على سايت جديد. لذلك ننشئها هنا
	مباشرة (idempotent) كي لا يعتمد نقل الحقول على معالج إعداد ERPNext.
	"""
	from al_khoms_edu import seed

	seed.make_custom_fields()


def after_install():
	"""يُستدعى عند تركيب التطبيق لأول مرة."""
	install_custom_fields()
	_install_seed_custom_fields()
	apply_phase1_setup()


def after_migrate():
	"""يُستدعى بعد كل migrate — يضمن إنشاء أي حقل مخصص جديد أُضيف للكود."""
	created = install_custom_fields()
	_install_seed_custom_fields()
	return created


# ----------------------------------------------------------------------
# 6) تعبئة البيانات القائمة (idempotent)
# ----------------------------------------------------------------------

def backfill_unified_numbers(limit=None):
	"""يُولّد رقم القيد الموحد لكل طالب لا يملكه (السجلات القديمة)."""
	if not _has_field("Student", "unified_registration_no"):
		return 0

	names = frappe.db.sql(
		"""select name from tabStudent
		   where ifnull(unified_registration_no,'')=''
		   order by creation asc""",
		pluck=True,
	)
	if limit:
		names = names[: int(limit)]

	updated = 0
	for name in names:
		doc = frappe.get_doc("Student", name)
		doc.unified_registration_no = build_unified_number(doc)
		doc.db_set(
			"unified_registration_no",
			doc.unified_registration_no,
			update_modified=False,
		)
		updated += 1
		if updated % 50 == 0:
			frappe.db.commit()
	frappe.db.commit()
	return updated


def sync_course_credits():
	"""ينسخ units إلى custom_credits حيث لم يُعبَّأ."""
	if not _has_field("Course", "custom_credits"):
		return 0
	frappe.db.sql(
		"""update tabCourse set custom_credits = ifnull(units,0)
		   where ifnull(custom_credits,0) = 0 and ifnull(units,0) > 0"""
	)
	frappe.db.commit()
	return frappe.db.sql(
		"select count(*) from tabCourse where ifnull(custom_credits,0) > 0"
	)[0][0]
