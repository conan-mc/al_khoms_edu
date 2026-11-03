# -*- coding: utf-8 -*-
"""سياسة الصلاحيات الأكاديمية المفصولة — Phase 1.

الفصل المعتمد:

    إدخال/تحرير المسودة  → Academics User
    الاعتماد/الإلغاء/التعديل بعد الاعتماد → Academics Manager
    الحذف النهائي        → System Manager فقط
    سجلات المحاولات      → تُنشأ آلياً، وقراءة فقط للبشر

تُطبَّق السياسة على DocPerm في قاعدة البيانات لأن DocTypes التقييم
والتسجيل تأتي من تطبيق education القياسي، ولا نعدّل ملفاته الأصلية.
"""

import frappe

# true = ممنوح، false = مسحوب. الحقول غير المذكورة تبقى كما هي.
POLICY = {
    "Assessment Result": {
        "Academics User": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 0,
            "cancel": 0,
            "delete": 0,
            "amend": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 1,
            "cancel": 1,
            "delete": 0,
            "amend": 1,
        },
        "Instructor": {"read": 1, "write": 0, "create": 0, "submit": 0,
                       "cancel": 0, "delete": 0, "amend": 0},
    },
    "Program Enrollment": {
        "Academics User": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 0,
            "cancel": 0,
            "delete": 0,
            "amend": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 1,
            "cancel": 1,
            "delete": 0,
            "amend": 1,
        },
    },
    "Course Enrollment": {
        "Academics User": {
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
        },
    },
    "Student": {
        "Academics User": {
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
        },
    },
    "Student Attempt Log": {
        "Academics User": {
            "read": 1,
            "write": 0,
            "create": 0,
            "delete": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 0,
            "create": 0,
            "delete": 0,
        },
    },
    "Student Semester Result": {
        "Academics User": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 0,
            "cancel": 0,
            "delete": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 1,
            "cancel": 1,
            "delete": 0,
        },
    },
    "Student Equivalence": {
        "Academics User": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 0,
            "cancel": 0,
            "delete": 0,
        },
        "Academics Manager": {
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 1,
            "cancel": 1,
            "delete": 0,
        },
    },
}


def _permission_rows(doctype, role):
    """كل صفوف الصلاحية للمستوى 0 — بعض السجلات القديمة بلا parentfield."""
    return frappe.get_all(
        "DocPerm",
        filters={
            "parent": doctype,
            "parenttype": "DocType",
            "role": role,
            "permlevel": 0,
        },
        pluck="name",
        order_by="creation asc",
    )


def _permission_row(doctype, role):
    rows = _permission_rows(doctype, role)
    if not rows:
        return None
    # فضّل الصف القياسي، وإلا أول صف قديم
    for name in rows:
        if frappe.db.get_value("DocPerm", name, "parentfield") == "permissions":
            return name
    return rows[0]


def _dedupe_permission_rows(doctype, role):
    """يدمج صفوف الصلاحية المكررة الناتجة عن إعدادات قديمة."""
    rows = _permission_rows(doctype, role)
    if len(rows) <= 1:
        return 0
    keep = _permission_row(doctype, role)
    removed = 0
    for name in rows:
        if name == keep:
            continue
        frappe.db.delete("DocPerm", {"name": name})
        removed += 1
    if not frappe.db.get_value("DocPerm", keep, "parentfield"):
        frappe.db.set_value("DocPerm", keep, "parentfield", "permissions")
    return removed


def _create_permission_row(doctype, role, flags):
    values = {
        "doctype": "DocPerm",
        "parent": doctype,
        "parenttype": "DocType",
        "parentfield": "permissions",
        "role": role,
        "permlevel": 0,
        "if_owner": 0,
        "email": 1 if flags.get("read") else 0,
        "export": 1 if flags.get("read") else 0,
        "print": 1 if flags.get("read") else 0,
        "report": 1 if flags.get("read") else 0,
        "share": 1 if flags.get("read") else 0,
    }
    for key in ("read", "write", "create", "submit", "cancel", "delete", "amend"):
        values[key] = 1 if flags.get(key) else 0
    doc = frappe.get_doc(values)
    doc.insert(ignore_permissions=True)
    return doc.name


def apply_academic_permissions():
    """يطبّق سياسة الفصل على DocPerm، ويُعيد ملخص التغييرات."""
    changed = created = deduped = 0
    for doctype, roles in POLICY.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for role, flags in roles.items():
            if not frappe.db.exists("Role", role):
                continue
            deduped += _dedupe_permission_rows(doctype, role)
            row = _permission_row(doctype, role)
            if not row:
                _create_permission_row(doctype, role, flags)
                created += 1
                continue
            current = frappe.db.get_value(
                "DocPerm", row, list(flags.keys()), as_dict=True
            ) or {}
            updates = {
                key: int(bool(value))
                for key, value in flags.items()
                if int(current.get(key) or 0) != int(bool(value))
            }
            if updates:
                frappe.db.set_value("DocPerm", row, updates)
                changed += 1
        frappe.clear_cache(doctype=doctype)

    frappe.clear_cache()
    return {"created": created, "changed": changed, "deduped": deduped}


def validate_academic_permissions():
    """يعيد قائمة انتهاكات المصفوفة المطلوبة (فارغة = مطابقة)."""
    mismatches = []
    for doctype, roles in POLICY.items():
        if not frappe.db.exists("DocType", doctype):
            mismatches.append({"doctype": doctype, "error": "DocType missing"})
            continue
        for role, flags in roles.items():
            row = _permission_row(doctype, role)
            if not row:
                mismatches.append(
                    {"doctype": doctype, "role": role, "error": "permission row missing"}
                )
                continue
            current = frappe.db.get_value(
                "DocPerm", row, list(flags.keys()), as_dict=True
            ) or {}
            for key, value in flags.items():
                if int(current.get(key) or 0) != int(bool(value)):
                    mismatches.append(
                        {
                            "doctype": doctype,
                            "role": role,
                            "permission": key,
                            "expected": int(bool(value)),
                            "actual": int(current.get(key) or 0),
                        }
                    )
    return mismatches
