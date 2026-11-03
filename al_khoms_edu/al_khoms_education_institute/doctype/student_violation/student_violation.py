# -*- coding: utf-8 -*-
"""وحدة النظام التأديبي — المواد 51 إلى 72 من اللائحة الداخلية.

تسجّل المخالفة وقرار مجلس التأديب، وتُطبّق العقوبة آلياً:
- إنذار كتابي          → وسم الطالب بـ«إنذار».
- إيقاف فصل / فصلين    → سجل «Student Suspension» + منع التسجيل.
- إلغاء نتيجة فصل      → تصفير نتائج الفصل + إعادة الفصل.
- فصل نهائي            → تعطيل ملف الطالب ومنع أي تسجيل.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, now_datetime

SUSPENSION_TERMS = {
	"إيقاف عن الدراسة فصل دراسي": 1,
	"إيقاف عن الدراسة فصلين دراسيين": 2,
}

FINAL_EXPULSION = "فصل نهائي"
CANCEL_TERM = "إلغاء نتيجة فصل دراسي"
WRITTEN_WARNING = "إنذار كتابي"

STATUS_DRAFT = "مسجلة"
STATUS_APPROVED = "معتمدة"
STATUS_CLOSED = "منتهية"
STATUS_CANCELLED = "ملغاة"

DISCIPLINE_CLEAN = "سليم"
DISCIPLINE_WARNING = "إنذار"
DISCIPLINE_SUSPENDED = "موقوف"
DISCIPLINE_EXPELLED = "مفصول"

SUSPENSION_ACTIVE = "موقوف"
SUSPENSION_RETURNED = "عاد للدراسة"


class StudentViolation(Document):
	def validate(self):
		self.suspension_terms = SUSPENSION_TERMS.get(self.decision, 0)

		if self.status == STATUS_APPROVED:
			if not self.decision_date:
				frappe.throw(_("أدخل تاريخ قرار مجلس التأديب قبل الاعتماد."))
			if not len(self.committee):
				frappe.throw(
					_("لا يمكن اعتماد العقوبة دون تسجيل أعضاء مجلس التأديب."),
					title=_("مجلس التأديب"),
				)
			if len(self.committee) < 3:
				frappe.throw(
					_("مجلس التأديب يجب أن يتكوّن من ثلاثة أعضاء على الأقل."),
					title=_("مجلس التأديب"),
				)
			refusals = [m.member_name for m in self.committee if m.vote == "غير موافق"]
			if refusals and len(refusals) >= len(self.committee) / 2:
				frappe.throw(
					_("لا تجوز المصادقة على العقوبة دون أغلبية موافقة؛ المعترضون: {0}").format(
						"، ".join(refusals)
					),
					title=_("قرار غير مكتمل"),
				)

		if self.decision in SUSPENSION_TERMS:
			if not (self.penalty_year and self.penalty_term):
				frappe.throw(
					_("حدّد سنة وفصل بداية سريان الإيقاف."),
					title=_("بيانات العقوبة"),
				)
			self._fill_end_term()

	# ------------------------------------------------------------------

	def on_update(self):
		if self.status == STATUS_APPROVED and not self.applied:
			self._apply_penalty()
		elif self.status in (STATUS_CLOSED, STATUS_CANCELLED) and self.applied:
			self._lift_penalty()

	def on_trash(self):
		if self.applied and self.status not in (STATUS_CLOSED, STATUS_CANCELLED):
			frappe.throw(
				_("لا يمكن حذف مخالفة مُطبَّقة؛ أنهاها أو ألغِها أولاً."),
				title=_("مخالفة تأديبية"),
			)

	# ------------------------------------------------------------------

	def _fill_end_term(self):
		if self.penalty_end_year and self.penalty_end_term:
			return
		terms = _ordered_terms()
		start = self.penalty_term
		if start not in terms:
			return
		idx = terms.index(start) + self.suspension_terms
		if idx < len(terms):
			term = terms[idx]
			self.penalty_end_term = term
			self.penalty_end_year = frappe.db.get_value("Academic Term", term, "academic_year")

	def _apply_penalty(self):
		frappe.flags.in_disciplinary_action = True
		try:
			if self.decision == WRITTEN_WARNING:
				self._set_status(DISCIPLINE_WARNING)

			elif self.decision in SUSPENSION_TERMS:
				self._suspend()

			elif self.decision == CANCEL_TERM:
				self._cancel_term_results()
				self._set_status(DISCIPLINE_WARNING)

			elif self.decision == FINAL_EXPULSION:
				self._expel()

		finally:
			frappe.flags.in_disciplinary_action = False

		self.db_set("applied", 1)
		self.db_set("applied_on", now_datetime())

	# ------------------------------------------------------------------

	def _suspend(self):
		existing = frappe.db.exists(
			"Student Suspension",
			{
				"student": self.student,
				"status": SUSPENSION_ACTIVE,
				"note": ["like", f"%{self.name}%"],
			},
		)
		if not existing:
			suspension = frappe.new_doc("Student Suspension")
			suspension.student = self.student
			suspension.student_name = self.student_name
			suspension.program = self._program()
			suspension.suspended_year = self.penalty_year
			suspension.suspended_term = self.penalty_term
			suspension.return_year = self.penalty_end_year
			suspension.return_term = self.penalty_end_term
			suspension.status = SUSPENSION_ACTIVE
			suspension.note = (
				f"عقوبة تأديبية — {self.name} | {self.decision}"
				+ (f" | {self.decision_note}" if self.decision_note else "")
			)
			# الإيقاف التأديبي لا يخضع لقاعدة «مرة واحدة في المسيرة»
			suspension.flags.ignore_validate = True
			suspension.insert(ignore_permissions=True)

		self._set_status(DISCIPLINE_SUSPENDED, is_suspended=1)

	def _cancel_term_results(self):
		if not (self.penalty_year and self.penalty_term):
			frappe.throw(_("حدّد السنة والفصل المطلوب إلغاء نتيجتهما."))

		results = frappe.get_all(
			"Assessment Result",
			filters={
				"student": self.student,
				"academic_year": self.penalty_year,
				"academic_term": self.penalty_term,
				"docstatus": 1,
			},
			pluck="name",
		)
		for name in results:
			frappe.db.set_value(
				"Assessment Result",
				name,
				{
					"total_score": 0,
					"course_work_score": 0,
					"final_exam_score": 0,
					"grade": "راسب",
					"is_deprived": 1,
					"deprivation_reason": f"إلغاء نتيجة الفصل — {self.name}",
				},
			)

		semester = frappe.db.get_value(
			"Student Semester Result",
			{
				"student": self.student,
				"academic_year": self.penalty_year,
				"academic_term": self.penalty_term,
			},
			"name",
		)
		if semester:
			frappe.db.set_value(
				"Student Semester Result",
				semester,
				{"semester_points": 0, "semester_average": 0, "status": "إعادة"},
			)

		frappe.msgprint(
			_("أُلغيت نتيجة الفصل: {0} سجل نتيجة.").format(len(results)),
			alert=True,
			indicator="orange",
		)

	def _expel(self):
		self._set_status(DISCIPLINE_EXPELLED, is_suspended=1)
		frappe.db.set_value("Student", self.student, "enabled", 0)
		frappe.db.set_value("Student", self.student, "date_of_leaving", nowdate())
		frappe.db.set_value(
			"Student",
			self.student,
			"reason_for_leaving",
			f"فصل نهائي بقرار مجلس التأديب — {self.name}",
		)

		existing = frappe.db.exists(
			"Student Suspension",
			{"student": self.student, "note": ["like", f"%{self.name}%"]},
		)
		if not existing:
			suspension = frappe.new_doc("Student Suspension")
			suspension.student = self.student
			suspension.student_name = self.student_name
			suspension.program = self._program()
			suspension.status = SUSPENSION_ACTIVE
			suspension.note = f"فصل نهائي — {self.name}"
			suspension.flags.ignore_validate = True
			suspension.insert(ignore_permissions=True)

	# ------------------------------------------------------------------

	def _lift_penalty(self):
		if self.decision == FINAL_EXPULSION and self.status == STATUS_CLOSED:
			frappe.msgprint(
				_("الفصل النهائي لا يُرفع آلياً؛ يلزم قرار صريح من الإدارة."),
				alert=True,
				indicator="red",
			)
			return

		if self.decision in SUSPENSION_TERMS:
			suspensions = frappe.get_all(
				"Student Suspension",
				filters={"student": self.student, "note": ["like", f"%{self.name}%"]},
				pluck="name",
			)
			for name in suspensions:
				frappe.db.set_value("Student Suspension", name, "status", SUSPENSION_RETURNED)

		# قد توجد عقوبة أخرى سارية أو وقف قيد أكاديمي مستقل
		other = frappe.db.exists(
			"Student Violation",
			{
				"student": self.student,
				"status": STATUS_APPROVED,
				"name": ["!=", self.name],
				"decision": ["in", list(SUSPENSION_TERMS) + [FINAL_EXPULSION]],
			},
		)
		if other:
			return

		active = frappe.db.exists(
			"Student Suspension",
			{"student": self.student, "status": SUSPENSION_ACTIVE},
		)
		self._set_status(DISCIPLINE_CLEAN, is_suspended=1 if active else 0)

	def _program(self):
		if self.program:
			return self.program
		return frappe.db.get_value(
			"Program Enrollment",
			{"student": self.student},
			"program",
			order_by="creation desc",
		)

	def _set_status(self, status, is_suspended=None):
		frappe.db.set_value("Student", self.student, "disciplinary_status", status)
		if is_suspended is not None:
			frappe.db.set_value("Student", self.student, "is_suspended", is_suspended)


# ----------------------------------------------------------------------
# أدوات مساعدة
# ----------------------------------------------------------------------

def _ordered_terms():
	"""يُرتّب الفصول زمنياً (سنة ثم خريف/ربيع)."""
	terms = frappe.get_all("Academic Term", fields=["name", "term_name", "academic_year"])
	keyed = []
	for term in terms:
		text = f"{term.term_name or ''} {term.academic_year or ''}"
		years = re.findall(r"\d{4}", text)
		year = int(years[0]) if years else 0
		season = 2 if "ربيع" in text else 1
		keyed.append(((year, season), term.name))
	keyed.sort()
	return [name for _, name in keyed]
