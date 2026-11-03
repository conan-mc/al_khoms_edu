# -*- coding: utf-8 -*-
"""توليد أرقام وطنية مؤقتة (Placeholder) للطلاب الذين لا يملكون رقماً وطنياً.

القواعد:
- البنية مطابقة لقواعد التحقق في validators.py:
  الخانة 1: الجنس (1 ذكر / 2 أنثى) — الخانات 2–5: سنة الميلاد (1900–2100)
  الخانات 6–8: ثابتة «999» (بصمة تميّز الأرقام المؤقتة)
  الخانات 9–12: تسلسل فريد (0001 فأكثر).
- يُستخدم الجنس وسنة الميلاد الفعليان عند وجودهما، وإلا فالافتراضي:
  الجنس «أنثى» (2) وسنة الميلاد 2000 — تُوثَّق الافتراضات في ملف التعيين.
- الجنس وتاريخ الميلاد في سجل الطالب لا يُمسّان — يُشتقان تلقائياً من
  الرقم الرسمي عند إدخاله لاحقاً (عبر validators.validate_national_id).
- يُوسم كل طالب بـ national_id_placeholder=1 لسهولة حصر الأرقام المؤقتة،
  ويُكتب ملف تعيين JSON في sites/<site>/private/files/

الاستخدام:
  bench --site erp.local execute al_khoms_edu.placeholder_national_ids.run
  bench --site erp.local execute al_khoms_edu.placeholder_national_ids.run --kwargs "{'confirm': True}"
"""

import json

import frappe
from frappe.utils import cint, getdate, now

from al_khoms_edu import validators

SEQUENCE_MARKER = "999"
DEFAULT_GENDER = validators.GENDER_FEMALE
DEFAULT_GENDER_DIGIT = "2"
DEFAULT_BIRTH_YEAR = 2000
MAPPING_FILENAME = "national_ids_placeholder.json"


def _target_students():
    students = frappe.get_all(
        "Student",
        fields=["name", "student_name", "gender", "date_of_birth", "national_id"],
        order_by="name asc",
        limit_page_length=0,
    )
    return [s for s in students if not (s.get("national_id") or "").strip()]


def _used_national_ids():
    rows = frappe.db.sql(
        "SELECT national_id FROM `tabStudent` "
        "WHERE national_id IS NOT NULL AND national_id != ''"
    )
    return {row[0] for row in rows}


def _birth_year(raw_dob):
    if not raw_dob:
        return DEFAULT_BIRTH_YEAR, True
    try:
        year = getdate(raw_dob).year
    except Exception:
        return DEFAULT_BIRTH_YEAR, True
    if not (1900 <= year <= 2100):
        return DEFAULT_BIRTH_YEAR, True
    return year, False


def build_plan():
    """يبني قائمة التعيينات دون كتابة أي تغيير."""
    used = _used_national_ids()
    plan = []
    seq = 1
    for student in _target_students():
        gender = student.gender if student.gender in (
            validators.GENDER_MALE, validators.GENDER_FEMALE
        ) else DEFAULT_GENDER
        assumed_gender = gender != student.gender
        digit = "1" if gender == validators.GENDER_MALE else DEFAULT_GENDER_DIGIT
        year, assumed_year = _birth_year(student.date_of_birth)

        while True:
            nid = f"{digit}{year:04d}{SEQUENCE_MARKER}{seq:04d}"
            seq += 1
            if nid not in used:
                break
        used.add(nid)

        plan.append({
            "student": student.name,
            "student_name": student.student_name,
            "national_id": nid,
            "gender": gender,
            "assumed_gender": assumed_gender,
            "birth_year": year,
            "assumed_birth_year": assumed_year,
        })
    return plan


def _write_mapping(plan):
    path = frappe.get_site_path("private", "files", MAPPING_FILENAME)
    payload = {
        "generated_at": now(),
        "format": (
            "[الجنس 1رقم][سنة الميلاد 4][999][تسلسل 4] = 12 رقماً — "
            "الخانات 6–8 ثابتة 999 لتمييز الأرقام المؤقتة"
        ),
        "defaults": {
            "gender": DEFAULT_GENDER,
            "birth_year": DEFAULT_BIRTH_YEAR,
        },
        "count": len(plan),
        "students": plan,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path


def run(confirm=False, limit_preview=8):
    """confirm=False: معاينة فقط — confirm=True: كتابة فعلية + ملف تعيين."""
    plan = build_plan()
    if not plan:
        print("لا يوجد طلاب بلا رقم وطني — لا شيء للتنفيذ.")
        return

    assumed_gender = sum(1 for r in plan if r["assumed_gender"])
    assumed_year = sum(1 for r in plan if r["assumed_birth_year"])
    print(
        f"عدد الطلاب المستهدفين: {len(plan)} | "
        f"جنس افتراضي: {assumed_gender} | سنة ميلاد افتراضية: {assumed_year}"
    )
    for row in plan[: max(cint(limit_preview), 0)]:
        print(
            f'  {row["student"]}  {row["student_name"]}  →  {row["national_id"]}'
            f'  ({row["gender"]}، {row["birth_year"]})'
        )

    if not confirm:
        print("معاينة فقط (confirm=False) — لم يُكتب أي تغيير.")
        return

    for row in plan:
        frappe.db.set_value(
            "Student",
            row["student"],
            {
                "national_id": row["national_id"],
                "national_id_placeholder": 1,
            },
            update_modified=False,
        )
    frappe.db.commit()

    path = _write_mapping(plan)
    print(f"تم تحديث {len(plan)} طالباً. ملف التعيين: {path}")
