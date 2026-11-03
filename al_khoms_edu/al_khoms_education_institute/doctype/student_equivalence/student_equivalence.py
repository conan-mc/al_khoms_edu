# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document


class StudentEquivalence(Document):
	def validate(self):
		if self.grade is not None and not (0 <= self.grade <= 100):
			course = self.course or ""
			frappe.throw(
				_("الدرجة المعادلة لمادة «{0}» يجب أن تكون بين 0 و 100؛ أدخلت: {1}.").format(
					course, self.grade
				),
				title=_("الدرجة المعادلة غير صحيحة"),
			)
