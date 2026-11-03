# -*- coding: utf-8 -*-
"""إضافة رمز QR للتحقق الإلكتروني إلى كشف الدرجات + إنشاء «صفحة المسؤول».

- يزامن قالب كشف الدرجات من الملف إلى سجل Print Format (لأن seed لا يستبدل
  السجلات الموجودة).
- ينشئ مساحة عمل «صفحة المسؤول» ويضبطها صفحةً افتراضية لأدوار الإدارة.

قابل للتنفيذ المتكرّر (idempotent).
"""

import os

import frappe

TRANSCRIPT_FORMAT = "كشف الدرجات"
TRANSCRIPT_FILE = "transcript.html"


def _sync_transcript_format():
    path = os.path.join(
        frappe.get_app_path("al_khoms_edu"), "templates", "print_formats", TRANSCRIPT_FILE
    )
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    if not frappe.db.exists("Print Format", TRANSCRIPT_FORMAT):
        return

    if (frappe.db.get_value("Print Format", TRANSCRIPT_FORMAT, "html") or "").strip() == html.strip():
        return

    doc = frappe.get_doc("Print Format", TRANSCRIPT_FORMAT)
    doc.html = html
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()


def execute():
    from al_khoms_edu import landing

    _sync_transcript_format()
    landing.setup()
