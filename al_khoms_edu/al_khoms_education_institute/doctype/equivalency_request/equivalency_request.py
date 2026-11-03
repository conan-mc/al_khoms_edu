# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document

MIN_MATCH = 75.0
MIN_MEMBERS = 3


class EquivalencyRequest(Document):
	def validate(self):
		self.validate_courses()
		self.validate_committee()
		if self.status == "معتمد":
			self.validate_approval()

	def on_update(self):
		if self.status == "معتمد" and not self.flags.equivalence_applied:
			self.apply_equivalence()
			self.flags.equivalence_applied = True

	# ------------------------------------------------------------------

	def validate_courses(self):
		seen = set()
		for row in self.courses:
			if row.syllabus_match_percent is None:
				frappe.throw(
					_("المادة «{0}»: يجب إدخال نسبة مطابقة المفردات.").format(row.course)
				)
			if row.syllabus_match_percent < MIN_MATCH:
				frappe.throw(
					_(
						"المادة «{0}»: نسبة مطابقة المفردات {1}% أقل من الحد الأدنى {2}% (مادة 8)."
					).format(row.course, row.syllabus_match_percent, int(MIN_MATCH)),
					title=_("معادلة مرفوضة"),
				)
			if row.is_equivalent and not row.source_score:
				frappe.throw(
					_("المادة «{0}»: يجب إدخال درجة الطالب في المعهد المصدر.").format(row.course)
				)
			if row.course in seen:
				frappe.throw(_("المادة «{0}» مكرّرة في الطلب.").format(row.course))
			seen.add(row.course)

	def validate_committee(self):
		if not len(self.committee):
			return
		if len(self.committee) < MIN_MEMBERS:
			frappe.throw(
				_("لجنة المعادلة يجب أن تتكوّن من ثلاثة أعضاء على الأقل (مادة 8)."),
				title=_("لجنة غير مكتملة"),
			)
		refusals = [m.member_name for m in self.committee if m.decision != "موافق"]
		if refusals:
			frappe.throw(
				_("المعادلة تحتاج موافقة جماعية؛ الأعضاء غير الموافقين: {0}").format(
					"، ".join(refusals)
				),
				title=_("لا موافقة جماعية"),
			)

	def validate_approval(self):
		if not len(self.committee):
			frappe.throw(_("لا يمكن اعتماد المعادلة دون تسجيل أعضاء اللجنة."))
		if not self.decision_date:
			frappe.throw(_("أدخل تاريخ قرار اللجنة قبل الاعتماد."))

	# ------------------------------------------------------------------

	def apply_equivalence(self):
		"""ينشئ Student Equivalence معتمدة لكل مادة، ويمنع التكرار."""
		created = 0
		for row in self.courses:
			if not row.is_equivalent:
				continue
			exists = frappe.db.exists(
				"Student Equivalence",
				{"student": self.student, "course": row.course, "docstatus": 1},
			)
			if exists:
				continue
			doc = frappe.new_doc("Student Equivalence")
			doc.student = self.student
			doc.student_name = self.student_name
			doc.course = row.course
			doc.grade = row.source_score
			doc.note = (
				f"معادلة {self.name} | {self.source_institute} | "
				f"مطابقة {row.syllabus_match_percent}%"
			)
			doc.insert(ignore_permissions=True)
			doc.submit()
			created += 1
		if created:
			frappe.msgprint(
				_("تم إنشاء {0} سجل معادلة معتمد.").format(created), alert=True
			)
