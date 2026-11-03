# -*- coding: utf-8 -*-
"""صفحة التحقق العامة /verify — تُفتح عند مسح رمز QR المطبوع على كشف الدرجات.

متاحة للجميع (بدون تسجيل دخول) لكنها لا تعمل إلا برابط موقّع صالح،
ولا تعرض سوى بيانات مختصرة (الاسم، رقم القيد، البرنامج، المعدل التراكمي).
"""

import frappe

from al_khoms_edu import verification

INSTITUTE = "المعهد العالي للعلوم والتقنية - الخمس"


def get_context(context):
    context.no_cache = 1
    context.valid = False
    context.reason = ""
    context.institute = INSTITUTE

    student = (frappe.form_dict.get("d") or "").strip()
    program = (frappe.form_dict.get("p") or "").strip() or None
    signature = (frappe.form_dict.get("s") or "").strip()

    if not student or not signature:
        context.reason = "رابط التحقق غير مكتمل."
        return

    if not frappe.db.exists("Student", student):
        context.reason = "لا يوجد سجل طالب مطابق."
        return

    if not verification.is_valid(student, program, signature):
        context.reason = "توقيع الوثيقة غير صالح — الرابط مُعدَّل أو غير صادر عن المعهد."
        return

    from al_khoms_edu import print_helpers

    data = print_helpers.transcript_context(student, program)
    context.valid = True
    context.student = data["student"]
    context.result = data["result"]
    context.semesters = len(data["blocks"])
    context.verified_on = frappe.utils.formatdate(frappe.utils.nowdate(), "dd/MM/yyyy")
