# -*- coding: utf-8 -*-
"""تحقّقات خاصة بالتطبيق تُسجّل عبر hooks.py"""

import re

import frappe
from frappe import _
from frappe.utils import format_date, getdate

NATIONAL_ID_RE = re.compile(r"^[0-9]{12}$")

GENDER_MALE = "ذكر"
GENDER_FEMALE = "أنثى"

# الأرقام العربية (٠١٢…٩) والفارسية (۰۱۲…۹) → الأرقام اللاتينية
_DIGIT_MAP = {ord(ch): str(i) for i, ch in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(ch): str(i) for i, ch in enumerate("۰۱۲۳۴۵۶۷۸۹")})

# المسافات والفواصل والعلامات الاتجاهية التي تُكتب أحياناً مع الرقم الوطني
_STRIPPED_CHARS = " \t\u00a0\u200b\u200e\u200f-\u2010\u2011\u2012\u2013\u2014"


def _normalize_national_id(value):
    """يحوّل الأرقام العربية/الفارسية إلى لاتينية ويزيل المسافات والفواصل.

    مثال: «١ ٢٣٤٥-٦٧٨٩٠١٢» → «123456789012»
    """
    text = str(value or "").translate(_DIGIT_MAP)
    return text.translate({ord(ch): None for ch in _STRIPPED_CHARS}).strip()


def validate_national_id(doc, method=None):
    """الرقم الوطني: 12 رقماً فقط، يبدأ بـ 1 (ذكر) أو 2 (أنثى).

    - تُقبل الأرقام العربية/الفارسية وتُحوَّل تلقائياً إلى لاتينية.
    - تُزال المسافات والفواصل (-) والعلامات الاتجاهية.
    - يُشتق منه تلقائياً: الجنس (للقراءة فقط) وسنة الميلاد داخل
      date_of_birth (يبقى اليوم/الشهر)، والحقل غير إلزامي.
    """
    raw = str(doc.get("national_id") or "")
    nid = _normalize_national_id(raw)

    if not nid:
        return

    invalid = sorted({ch for ch in nid if not ("0" <= ch <= "9")})
    if invalid:
        chars = "، ".join(f"«{ch}»" for ch in invalid)
        frappe.throw(
            _(
                "الرقم الوطني يجب أن يتكوّن من 12 رقماً فقط — لا يُسمح بالحروف أو الرموز."
                "<br>الحروف/الرموز غير المسموحة: {0}"
            ).format(chars),
            title=_("الرقم الوطني غير صحيح"),
        )

    if len(nid) != 12:
        frappe.throw(
            _("الرقم الوطني يجب أن يتكوّن من 12 رقماً؛ أدخلت {0} رقماً فقط.").format(len(nid)),
            title=_("الرقم الوطني غير صحيح"),
        )

    first = nid[0]
    if first not in ("1", "2"):
        frappe.throw(
            _(
                "الرقم الوطني يجب أن يبدأ بـ 1 (ذكر) أو 2 (أنثى)؛ "
                "الرقم الذي أدخلته يبدأ بـ «{0}»."
            ).format(first),
            title=_("الرقم الوطني غير صحيح"),
        )

    _ensure_national_id_is_unique(doc, nid)

    doc.national_id = nid

    if nid[5:8] != "999":
        doc.national_id_placeholder = 0

    old_gender = doc.get("gender")
    old_dob = str(doc.get("date_of_birth") or "")

    doc.gender = GENDER_MALE if first == "1" else GENDER_FEMALE
    _apply_birth_year(doc, int(nid[1:5]))

    # مزامنة المستخدم المرتبط إن وُجد (تغيير الرقم الوطني لاحقاً)
    if doc.get("user") and frappe.db.exists("User", doc.user):
        frappe.db.set_value(
            "User", doc.user, "gender", doc.gender, update_modified=False
        )

    _notify_derived_values(doc, raw, old_gender, old_dob)


def _ensure_national_id_is_unique(doc, nid):
    """رسالة عربية واضحة بدل خطأ قاعدة البيانات عند تكرار الرقم الوطني."""
    filters = {"national_id": nid}
    if doc.name:
        filters["name"] = ["!=", doc.name]

    other = frappe.db.get_value("Student", filters, ["name", "student_name"], as_dict=True)
    if other:
        frappe.throw(
            _("الرقم الوطني {0} مسجّل مسبقاً للطالب {1} ({2}).").format(
                nid, other.student_name or "", other.name
            ),
            title=_("رقم وطني مكرر"),
        )


def _apply_birth_year(doc, year):
    """يضبط سنة الميلاد في date_of_birth مع الإبقاء على اليوم والشهر الحاليين."""
    if year < 1900 or year > 2100:
        frappe.throw(
            _(
                "السنة المستخرجة من الرقم الوطني ({0}) غير منطقية — "
                "يجب أن تكون بين 1900 و 2100. تحقق من الخانات 2–5."
            ).format(year),
            title=_("الرقم الوطني غير صحيح"),
        )

    current = doc.get("date_of_birth")
    if not current:
        doc.date_of_birth = f"{year:04d}-01-01"
        return

    try:
        current = getdate(current)
        doc.date_of_birth = current.replace(year=year)
    except ValueError:
        # 29 فبراير في سنة غير كبيسة
        doc.date_of_birth = current.replace(year=year, day=28)
    except Exception:
        doc.date_of_birth = f"{year:04d}-01-01"


def _notify_derived_values(doc, raw, old_gender, old_dob):
    """يُظهر ملاحظة عند تنسيق الرقم أو اشتقاق قيمة جديدة منه."""
    if frappe.flags.in_import or getattr(frappe.flags, "in_migrate", False):
        return

    notes = []
    if doc.get("national_id") != raw.strip():
        notes.append(_("تم تنسيق الرقم الوطني تلقائياً (تحويل الأرقام العربية وإزالة المسافات)."))
    if doc.get("gender") != old_gender:
        notes.append(_("الجنس (مشتق من الرقم الوطني): {0}").format(doc.gender))
    if str(doc.get("date_of_birth") or "") != old_dob:
        notes.append(_("سنة الميلاد (مشتقة من الرقم الوطني): {0}").format(format_date(doc.date_of_birth)))

    if notes:
        frappe.msgprint(
            "<br>".join(notes),
            title=_("تم التحديث من الرقم الوطني"),
            indicator="blue",
            alert=True,
        )
