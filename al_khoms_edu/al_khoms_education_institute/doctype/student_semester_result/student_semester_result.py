# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document

from al_khoms_edu import academic_rules as rules


class StudentSemesterResult(Document):
	def validate(self):
		self._check_duplicate()
		if not (frappe.flags.in_import or frappe.flags.in_migrate):
			self._auto_compute()
		self._validate_percentage("semester_average", "المعدل الفصلي")
		self._validate_percentage("cumulative_average", "المعدل التراكمي")
		for fieldname, label in (
			("semester_units", "الوحدات الفصلية"),
			("semester_points", "النقاط الفصلية"),
			("cumulative_units", "الوحدات التراكمية"),
			("cumulative_points", "النقاط التراكمية"),
			("accomplished_units", "الوحدات المنجزة"),
		):
			self._check_non_negative(fieldname, label)

	def _check_duplicate(self):
		"""سجل واحد فقط لكل (طالب، سنة دراسية، فصل) — يمنع التكرار المزدوج."""
		filters = {
			"student": self.student,
			"academic_year": self.academic_year,
			"academic_term": self.academic_term,
		}
		if self.name:
			filters["name"] = ["!=", self.name]

		existing = frappe.db.exists("Student Semester Result", filters)
		if existing:
			frappe.throw(
				_(
					"سجل نتيجة الفصل مسجّل مسبقاً للطالب {0} في {1} — {2} (السجل {3})."
				).format(self.student, self.academic_year, self.academic_term, existing),
				title=_("نتيجة فصلية مكررة"),
			)

	def _auto_compute(self):
		"""§ 2.8 — احتساب تلقائي من نتائج الطالب عند وجودها في الفصل."""
		result = rules.compute_semester_result(self.student, self.academic_term, self.program)
		if not result:
			return

		changed = any(
			abs(float(self.get(field) or 0) - float(value or 0)) > 0.001
			for field, value in result.items()
		)
		for field, value in result.items():
			self.set(field, value)

		if changed:
			frappe.msgprint(
				_(
					"تم احتساب المعدلات والحالة تلقائياً من نتائج الطالب — "
					"الفصلي: {0}% | التراكمي: {1}% | الوحدات المنجزة: {2} | الحالة: {3}"
				).format(
					result["semester_average"],
					result["cumulative_average"],
					result["accomplished_units"],
					_(result["status"]),
				),
				title=_("احتساب تلقائي"),
				indicator="blue",
				alert=True,
			)

	def _validate_percentage(self, fieldname, label):
		value = self.get(fieldname)
		if value is None:
			return
		value = float(value)
		if not (0 <= value <= 100):
			frappe.throw(
				_("{0} يجب أن يكون بين 0 و 100؛ أدخلت: {1}.").format(_(label), self.get(fieldname)),
				title=_("قيمة غير صحيحة"),
			)

	def _check_non_negative(self, fieldname, label):
		value = self.get(fieldname)
		if value is None:
			return
		if float(value) < 0:
			frappe.throw(
				_("{0} لا يمكن أن تكون قيمة سالبة؛ أدخلت: {1}.").format(_(label), self.get(fieldname)),
				title=_("قيمة غير صحيحة"),
			)
