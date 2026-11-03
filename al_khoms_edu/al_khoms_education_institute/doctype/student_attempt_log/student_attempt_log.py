# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document

from al_khoms_edu.academic_rules import get_rules


class StudentAttemptLog(Document):
	def validate(self):
		self._validate_attempt_number()
		self._validate_score()
		self._derive_passed()
		self._check_duplicate_attempt()
		self._check_expulsion()

	def _validate_attempt_number(self):
		if not self.attempt_number or self.attempt_number < 1:
			frappe.throw(
				_("رقم المحاولة يجب أن يكون 1 أو أكثر."),
				title=_("رقم المحاولة غير صحيح"),
			)

	def _validate_score(self):
		if self.score is None:
			return
		score = float(self.score)
		if not (0 <= score <= 100):
			frappe.throw(
				_("درجة المحاولة يجب أن تكون بين 0 و 100؛ أدخلت: {0}.").format(self.score),
				title=_("الدرجة غير صحيحة"),
			)

	def _derive_passed(self):
		"""يُحدَّد النجاح تلقائياً من الدرجة (حد النجاح من الإعدادات)."""
		old_passed = self.passed
		ps = get_rules().pass_score
		self.passed = 1 if float(self.score or 0) >= ps else 0

		if self.passed != old_passed and not frappe.flags.in_import:
			state = _("ناجح") if self.passed else _("راسب")
			frappe.msgprint(
				_("تم ضبط حالة المحاولة تلقائياً إلى «{0}» لأن حد النجاح هو {1}.").format(state, ps),
				title=_("حالة المحاولة"),
				indicator="blue",
				alert=True,
			)

	def _check_duplicate_attempt(self):
		filters = {
			"student": self.student,
			"course": self.course,
			"attempt_number": self.attempt_number,
		}
		if self.name:
			filters["name"] = ["!=", self.name]

		existing = frappe.db.exists("Student Attempt Log", filters)
		if existing:
			frappe.throw(
				_("رقم المحاولة {0} مسجّل مسبقاً لهذا الطالب في مادة «{1}» (السجل {2}).").format(
					self.attempt_number, self.course, existing
				),
				title=_("محاولة مكررة"),
			)

	def _check_expulsion(self):
		"""يمنع تسجيل محاولة جديدة لطالب استُنفدت محاولاته (§ 2.6)."""
		if not self.is_new() or frappe.flags.in_import:
			return

		from al_khoms_edu.academic_rules import get_attempt_status

		rules = get_rules()
		if get_attempt_status(self.student, self.course) == rules.attempt_status_expulsion:
			frappe.throw(
				_(
					"لا يمكن تسجيل محاولة جديدة: الطالب رسب في مادة «{0}» {1} مرات — "
					"يستوجب الفصل من المعهد وفق § 2.6."
				).format(self.course, rules.expulsion_attempt),
				title=_("تجاوز عدد محاولات المادة"),
			)
