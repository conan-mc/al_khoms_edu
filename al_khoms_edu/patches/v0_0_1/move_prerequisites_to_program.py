# -*- coding: utf-8 -*-
"""ينقل جدول المتطلبات من Program Course (غير صالح: جدول داخل جدول) إلى Program."""

import frappe

from al_khoms_edu.seed import CUSTOM_FIELDS


def execute():
	old = frappe.db.get_value(
		"Custom Field", {"dt": "Program Course", "fieldname": "prerequisites"}
	)
	if old:
		frappe.delete_doc("Custom Field", old, force=True, ignore_permissions=True)

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	frappe.db.commit()
