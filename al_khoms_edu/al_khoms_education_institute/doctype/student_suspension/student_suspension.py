# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document

from al_khoms_edu.academic_rules import get_rules


class StudentSuspension(Document):
	def validate(self):
		student = frappe.get_doc("Student", self.student)
		is_active = self.status == get_rules().suspension_status

		# § 2.5 — يُسمح بوقف القيد مرة واحدة فقط طوال مسيرة الطالب
		if is_active and student.suspension_used:
			frappe.throw(
				_("لا يمكن وقف قيد الطالب {0} مرة أخرى — استُخدم حق وقف القيد مسبقاً.").format(
					self.student
				),
				title=_("وقف القيد"),
			)

		# منع وجود وقفين نشطين في نفس الوقت
		if is_active:
			other = frappe.db.exists(
				"Student Suspension",
				{"student": self.student, "status": get_rules().suspension_status, "name": ["!=", self.name]},
			)
			if other:
				frappe.throw(
					_("يوجد سجل وقف قيد نشط بالفعل لهذا الطالب: {0}").format(other),
					title=_("وقف القيد"),
				)

	def on_update(self):
		student = frappe.get_doc("Student", self.student)
		if self.status == get_rules().suspension_status:
			student.db_set("is_suspended", 1)
		else:
			student.db_set("is_suspended", 0)
			if not student.suspension_used:
				student.db_set("suspension_used", 1)

	def on_trash(self):
		student = frappe.get_doc("Student", self.student)
		if self.status == get_rules().suspension_status:
			student.db_set("is_suspended", 0)
