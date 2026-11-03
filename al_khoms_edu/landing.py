# -*- coding: utf-8 -*-
"""landing.py — مساحات العمل المخصّصة لكل دور والصفحة الافتراضية عند الدخول.

- «صفحة المسؤول»: مساحة عمل Desk لدور الإدارة الأكاديمية (تحكّم كامل).
- الطلاب لا يملكون صلاحية Desk (نوعهم Website User)، وصفحتهم تُنفَّذ منفصلة.

يُشغَّل مرة واحدة عبر: bench --site erp.local execute al_khoms_edu.landing.setup
وهو قابل للتنفيذ المتكرّر (idempotent).
"""

import json

import frappe

ADMIN_WORKSPACE = "صفحة المسؤول"
ADMIN_ROLES = ("Academics Manager", "Academics User", "System Manager")
ADMIN_MODULE = "Al Khoms Education Institute"

ADMIN_SHORTCUTS = [
    ("Student", "الطلاب", "education"),
    ("Program Enrollment", "تسجيل البرامج", "students"),
    ("Course Enrollment", "تسجيل المواد", "book"),
    ("Assessment Result", "نتائج التقييم", "edit"),
    ("Student Semester Result", "نتائج الفصول", "milestone"),
]

# (نوع البطاقة، [(العنوان، نوع الرابط، الهدف)])
ADMIN_CARDS = [
    ("الطلاب والتسجيل", [
        ("Student", "DocType", "Student"),
        ("Program Enrollment", "DocType", "Program Enrollment"),
        ("Course Enrollment", "DocType", "Course Enrollment"),
        ("Student Group", "DocType", "Student Group"),
    ]),
    ("النتائج والدرجات", [
        ("Assessment Result", "DocType", "Assessment Result"),
        ("Student Semester Result", "DocType", "Student Semester Result"),
        ("Student Attempt Log", "DocType", "Student Attempt Log"),
    ]),
    ("الشؤون التأديبية والمعادلات", [
        ("Student Violation", "DocType", "Student Violation"),
        ("Student Suspension", "DocType", "Student Suspension"),
        ("Equivalency Request", "DocType", "Equivalency Request"),
        ("Student Equivalence", "DocType", "Student Equivalence"),
    ]),
    ("الخطط والبرامج", [
        ("Program", "DocType", "Program"),
        ("Course", "DocType", "Course"),
        ("Program Course", "DocType", "Program Course"),
        ("Course Prerequisite", "DocType", "Course Prerequisite"),
    ]),
]


def _block(block_id, block_type, data):
    return {"id": block_id, "type": block_type, "data": data}


def _build_content():
    """محتوى مساحة العمل (JSON) — ترويسة + اختصارات + بطاقات روابط."""
    content = [
        _block("adm-h", "header", {"text": '<span class="h4"><b>صفحة المسؤول</b></span>', "col": 12}),
        _block("adm-sp", "spacer", {"col": 12}),
    ]
    for i, (_dt, label, _icon) in enumerate(ADMIN_SHORTCUTS, start=1):
        content.append(_block(f"adm-sc-{i}", "shortcut", {"shortcut_name": label, "col": 3}))
    content.append(_block("adm-sp2", "spacer", {"col": 12}))
    for i, (card_label, _links) in enumerate(ADMIN_CARDS, start=1):
        content.append(_block(f"adm-cd-{i}", "card", {"card_name": card_label, "col": 4}))
    return json.dumps(content, ensure_ascii=False)


def _workspace_doc():
    if frappe.db.exists("Workspace", ADMIN_WORKSPACE):
        doc = frappe.get_doc("Workspace", ADMIN_WORKSPACE)
    else:
        doc = frappe.new_doc("Workspace")
        doc.label = ADMIN_WORKSPACE
    doc.title = ADMIN_WORKSPACE
    doc.public = 1
    doc.is_hidden = 0
    doc.icon = "organization"
    doc.module = ADMIN_MODULE
    doc.content = _build_content()

    doc.set("roles", [])
    for role in ADMIN_ROLES:
        if frappe.db.exists("Role", role):
            doc.append("roles", {"role": role})

    doc.set("shortcuts", [])
    for doc_type, label, icon in ADMIN_SHORTCUTS:
        doc.append("shortcuts", {
            "type": "DocType",
            "link_to": doc_type,
            "label": label,
            "icon": icon,
            "color": "Grey",
        })

    doc.set("links", [])
    for card_label, links in ADMIN_CARDS:
        doc.append("links", {"type": "Card Break", "label": card_label})
        for label, link_type, target in links:
            doc.append("links", {"type": "Link", "label": label, "link_type": link_type, "link_to": target})
    return doc


def _set_default_workspace(user, workspace):
    if frappe.db.get_value("User", user, "default_workspace") == workspace:
        return False
    frappe.db.set_value("User", user, "default_workspace", workspace, update_modified=False)
    return True


def apply_role_landing(login_manager=None):
    """يُستدعى عند كل تسجيل دخول: يضبط الصفحة الافتراضية حسب الدور.

    لا يستبدل اختيارًا صريحًا للمستخدم — يضبط فقط إذا كانت القيمة فارغة.
    """
    user = frappe.session.user
    if not user or user in ("Guest", "Administrator"):
        return
    if frappe.db.get_value("User", user, "default_workspace"):
        return
    roles = set(frappe.get_roles(user))
    if roles & set(ADMIN_ROLES) and frappe.db.exists("Workspace", ADMIN_WORKSPACE):
        if _set_default_workspace(user, ADMIN_WORKSPACE):
            frappe.cache.delete_value("home_page")


def setup():
    """ينشئ مساحة عمل المسؤول ويضبطها افتراضيًا لكل مستخدمي الأدوار الإدارية."""
    doc = _workspace_doc()
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    updated = 0
    for user in frappe.get_all("Has Role", filters={"role": ["in", ADMIN_ROLES]}, pluck="parent"):
        if not frappe.db.exists("User", user) or user in ("Guest", "Administrator"):
            continue
        if frappe.db.get_value("User", user, "user_type") != "System User":
            continue
        if _set_default_workspace(user, ADMIN_WORKSPACE):
            updated += 1
    frappe.db.commit()
    frappe.cache.delete_value("home_page")
    print(f"✓ مساحة العمل «{ADMIN_WORKSPACE}» جاهزة | مستخدمون تم ضبط صفحتهم: {updated}")
    return {"workspace": doc.name, "users_updated": updated}
