# -*- coding: utf-8 -*-
"""Helpers مشتركة لسكربتات ترحيل بيانات MS Access القديمة.

قاعدة Access الأصلية (جدول `degree`) لا تأتي مع المستودع. لتفعيل الترحيل
اضبط مسار المصدر في إعدادات الموقع::

    bench --site erp.local set-config access_db_path /path/to/old.mdb
    # أو ملف CSV مُصدَّر من Access:
    bench --site erp.local set-config access_db_path /path/to/degree.csv
    # اختياري: اسم الجدول (افتراضي degree)
    bench --site erp.local set-config access_table degree
"""

import csv
import os
import shutil
import subprocess

import frappe

# ---------------------------------------------------------------------------
# خرائط الأقسام / البرامج
# ---------------------------------------------------------------------------

COMP_DEPTS = {
	"قواعد البيانات": "قواعد البيانات",
	"تقنية المعلومات": "تقنية المعلومات",
	"الشبكات": "الشبكات",
}

_DEPT_ALIASES = {
	"1": "قواعد البيانات",
	"cd": "قواعد البيانات",
	"db": "قواعد البيانات",
	"dbms": "قواعد البيانات",
	"قواعد": "قواعد البيانات",
	"2": "تقنية المعلومات",
	"it": "تقنية المعلومات",
	"تقنية": "تقنية المعلومات",
	"3": "الشبكات",
	"net": "الشبكات",
	"network": "الشبكات",
	"networks": "الشبكات",
	"شبكات": "الشبكات",
}


# ---------------------------------------------------------------------------
# أدوات عامة
# ---------------------------------------------------------------------------

def ar(value):
	"""تحويل قيمة Access (قد تكون None) إلى نصّ آمن."""
	if value is None:
		return ""
	return str(value).strip()


def get_program(dept_type):
	"""يحوّل قيمة `dept_type` في Access إلى اسم برنامج Frappe، أو None."""
	raw = ar(dept_type)
	key = raw.lower()
	return _DEPT_ALIASES.get(key) or COMP_DEPTS.get(raw)


def class_to_level(class_no):
	"""يحوّل رقم الصف/المستوى في Access إلى رقم سنة (1..N)."""
	try:
		return int(float(ar(class_no)))
	except (TypeError, ValueError):
		return None


def time_to_term_name(value):
	"""يحوّل قيمة الفصل في Access إلى 'خريف' أو 'ربيع'."""
	s = ar(value).lower()
	if s in ("1", "خريف", "الخريف", "fall", "autumn"):
		return "خريف"
	if s in ("2", "ربيع", "الربيع", "spring"):
		return "ربيع"
	return None


def map_subject_code(code):
	"""تطبيع رمز المادة: إزالة المسافات وتوحيد الحروف."""
	return ar(code).upper().replace(" ", "").strip()


# ---------------------------------------------------------------------------
# قراءة قاعدة Access
# ---------------------------------------------------------------------------

class AccessParser:
	"""قارئ بسيط لجدول واحد من قاعدة Access أو من ملف CSV مُصدَّر."""

	def __init__(self, path, table="degree"):
		self.path = path
		self.table = table

	def load(self, table=None):
		table = table or self.table
		if self.path.lower().endswith(".csv"):
			with open(self.path, newline="", encoding="utf-8") as fobj:
				return [dict(row) for row in csv.DictReader(fobj)]

		if not shutil.which("mdb-export"):
			frappe.throw(
				"قراءة ملفات Access (.mdb/.accdb) تتطلب تثبيت mdbtools "
				"(mdb-export). بدلاً من ذلك صدّر الجدول إلى CSV واضبط access_db_path."
			)
		output = subprocess.check_output(["mdb-export", self.path, table]).decode(
			"utf-8", errors="replace"
		)
		return [dict(row) for row in csv.DictReader(output.splitlines())]


def get_access_parser():
	"""يُعيد قارئ قاعدة Access وفق إعدادات الموقع."""
	path = frappe.conf.get("access_db_path")
	if not path:
		frappe.throw(
			"لم يُضبط access_db_path. اضبطه قبل الترحيل: "
			"bench --site <site> set-config access_db_path /path/to/old.mdb"
		)
	if not os.path.exists(path):
		frappe.throw(f"مسار قاعدة Access غير موجود: {path}")
	table = frappe.conf.get("access_table") or "degree"
	return AccessParser(path, table)


def load_degree():
	"""يُحمّل كل صفوف جدول `degree` من مصدر Access."""
	return get_access_parser().load()
