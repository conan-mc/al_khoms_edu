# -*- coding: utf-8 -*-
"""يطبّق سياسة Phase 1 على موقع قائم: الفصل الإجباري + فصل الصلاحيات."""

import frappe

from al_khoms_edu.regulations import apply_phase1_setup, install_custom_fields


def execute():
    install_custom_fields()
    apply_phase1_setup()
    frappe.db.commit()
