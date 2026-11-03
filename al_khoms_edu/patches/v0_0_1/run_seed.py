# -*- coding: utf-8 -*-
"""يطبّق تهيئة al_khoms_edu تلقائياً (الحقول المخصصة، الجنس/الجنسية، البيانات الأساسية).

آمن للاستدعاء المتكرّر (idempotent) ولا يفشل الترحيل إذا لم تتوفر المتطلبات بعد
(تطبيق education أو وجود شركة) — يتخطّى مع رسالة واضحة.
"""

import frappe


def execute():
    installed = frappe.get_installed_apps()
    if "education" not in installed or "erpnext" not in installed:
        print("al_khoms_edu.seed: تم التخطي (تطبيقات education/erpnext غير مثبتة).")
        return

    if not frappe.db.exists("DocType", "Student"):
        print("al_khoms_edu.seed: تم التخطي (DocType Student غير موجود).")
        return

    if not frappe.db.count("Company"):
        print(
            "al_khoms_edu.seed: تم التخطي (لا توجد شركة). "
            "أنشئ شركة المعهد ثم أعد تنفيذ bench migrate."
        )
        return

    from al_khoms_edu import seed

    try:
        seed.run()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "al_khoms_edu seed patch failed")
        print("al_khoms_edu.seed: فشل التنفيذ — راجع Error Log.")
