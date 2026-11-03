"""
Al Khoms Education Institute - setup module.
يُنشئ الحقول المخصصة ويُهيئ البنية الأساسية (سنة، فصول، قسم، برامج، مواد).

Run:
    bench --site erp.local execute al_khoms_edu.seed.run
    bench --site erp.local execute al_khoms_edu.seed.make_custom_fields
"""

import frappe

from al_khoms_edu import plans_data

# ---------------------------------------------------------------------------
# Custom Fields
# ---------------------------------------------------------------------------

CUSTOM_FIELDS = {
    # -------------------------------------------------------------------
    # Course — رمز المقرر + الوحدات + الساعات + الرموز البديلة
    # -------------------------------------------------------------------
    "Course": [
        {
            "fieldname": "course_code",
            "label":     "رمز المقرر",
            "fieldtype": "Data",
            "insert_after": "course_name",
            "in_list_view": 1,
            "in_standard_filter": 1,
            # ملاحظة: لا unique — الرموز تتكرر بين الشعب/الخطط (نفس الرمز لاسمين)
        },
        {
            "fieldname": "is_general",
            "label":     "مادة عامة (الفصل الأول)",
            "fieldtype": "Check",
            "insert_after": "course_code",
        },
        {
            "fieldname": "cb_ah_1",
            "fieldtype": "Column Break",
            "insert_after": "is_general",
        },
        {
            "fieldname": "units",
            "label":     "الوحدات",
            "fieldtype": "Int",
            "insert_after": "cb_ah_1",
            "in_list_view": 1,
        },
        {
            "fieldname": "theory_hours",
            "label":     "الساعات النظرية",
            "fieldtype": "Float",
            "insert_after": "units",
        },
        {
            "fieldname": "practical_hours",
            "label":     "الساعات العملية",
            "fieldtype": "Float",
            "insert_after": "theory_hours",
        },
        {
            "fieldname": "tutorial_hours",
            "label":     "ساعات التمارين",
            "fieldtype": "Float",
            "insert_after": "practical_hours",
        },
        {
            "fieldname": "course_codes",
            "label":     "رموز المقرر (بديلة/سابقة)",
            "fieldtype": "Table",
            "options":   "Course Alternate Code",
            "insert_after": "tutorial_hours",
        },
    ],

    # -------------------------------------------------------------------
    # Program Course — فصل + متطلبات متعددة
    # -------------------------------------------------------------------
    "Program Course": [
        {
            "fieldname": "semester",
            "label":     "الفصل الدراسي",
            "fieldtype": "Int",
            "insert_after": "course_name",
            "in_list_view": 1,
        },
        {
            "fieldname": "prerequisite_course",
            "label":     "المتطلب السابق (مفرد - للتوافق)",
            "fieldtype": "Link",
            "options":   "Course",
            "insert_after": "semester",
            "hidden": 1,
        },
    ],

    # -------------------------------------------------------------------
    # Program — متطلبات المواد (جدول أبناء على مستوى البرنامج)
    # -------------------------------------------------------------------
    "Program": [
        {
            "fieldname": "prerequisites",
            "label":     "متطلبات المواد السابقة",
            "fieldtype": "Table",
            "options":   "Program Prerequisite",
            "insert_after": "courses",
        },
    ],

    # -------------------------------------------------------------------
    # Student — حقول الترحيل + وقف القيد
    # -------------------------------------------------------------------
    "Student": [
        {
            "fieldname": "legacy_student_number",
            "label":     "الرقم الجامعي القديم",
            "fieldtype": "Data",
            "insert_after": "student_name",
            "in_list_view": 1,
            "in_standard_filter": 1,
            "unique": 0,
        },
        {
            "fieldname": "national_id",
            "label":     "الرقم الوطني",
            "fieldtype": "Data",
            "insert_after": "birth_place_ak",
            "reqd": 1,
            "unique": 1,
            "description": "12 رقماً تبدأ بـ 1 (ذكر) أو 2 (أنثى). تُقبل الأرقام العربية وتُحوَّل تلقائياً، وتُزال المسافات والفواصل. يُشتق منها الجنس وسنة الميلاد آلياً.",
        },
        {
            "fieldname": "national_id_placeholder",
            "label":     "رقم وطني مؤقت (مولَّد آلياً)",
            "fieldtype": "Check",
            "insert_after": "national_id",
            "read_only": 1,
            "description": "يُعلَّم آلياً للأرقام المؤقتة — يمكّن من حصر الأرقام المستبدلة عند توفر الأرقام الرسمية",
        },
        {
            "fieldname": "birth_place_ak",
            "label":     "مكان الميلاد",
            "fieldtype": "Link",
            "options":   "Birth Place",
            "insert_after": "date_of_birth",
        },
        {
            "fieldname": "is_suspended",
            "label":     "موقوف القيد",
            "fieldtype": "Check",
            "insert_after": "legacy_student_number",
            "in_list_view": 0,
            "description": "§ 2.5 — يحق للطالب وقف قيد فصل واحد فقط طوال مسيرته",
        },
        {
            "fieldname": "suspension_used",
            "label":     "استُخدم وقف القيد مسبقاً",
            "fieldtype": "Check",
            "insert_after": "is_suspended",
            "read_only": 1,
            "description": "يُضبط تلقائياً عند رفع وقف القيد — لا يمكن الوقف مرة ثانية",
        },
        {
            "fieldname": "promotion_status",
            "label":     "حالة الترقية",
            "fieldtype": "Select",
            "options":   "\nترقية\nترقية مع ترحيل\nإعادة فصل",
            "insert_after": "suspension_used",
            "read_only": 1,
            "description": "تُحدَّث تلقائياً بواسطة مهمة الترقية الأسبوعية",
        },
        {
            "fieldname": "exempt",
            "label":     "مستثنى من المتطلبات السابقة",
            "fieldtype": "Check",
            "insert_after": "promotion_status",
            "description": "عند تفعيله يتجاوز النظام فحص المتطلبات السابقة لهذا الطالب",
        },

        # -- تبويب مستقل: السجل الأكاديمي --------------------------------
        {
            "fieldname": "academic_record_tab",
            "label":     "السجل الأكاديمي",
            "fieldtype": "Tab Break",
            "insert_after": "connections_tab",
        },
        {
            "fieldname": "academic_record_section",
            "fieldtype": "Section Break",
            "insert_after": "academic_record_tab",
        },
        {
            "fieldname": "cumulative_units_ak",
            "label":     "مجموع الوحدات التراكمي",
            "fieldtype": "Float",
            "insert_after": "academic_record_section",
        },
        {
            "fieldname": "cumulative_points_ak",
            "label":     "مجموع النقاط التراكمي",
            "fieldtype": "Float",
            "insert_after": "cumulative_units_ak",
        },
        {
            "fieldname": "cumulative_average_ak",
            "label":     "المعدل التراكمي",
            "fieldtype": "Float",
            "insert_after": "cumulative_points_ak",
        },
        {
            "fieldname": "academic_record_col",
            "fieldtype": "Column Break",
            "insert_after": "cumulative_average_ak",
        },
        {
            "fieldname": "previous_qualification",
            "label":     "المؤهل السابق",
            "fieldtype": "Data",
            "insert_after": "academic_record_col",
        },
        {
            "fieldname": "prev_qual_date",
            "label":     "تاريخ الحصول على المؤهل السابق",
            "fieldtype": "Date",
            "insert_after": "previous_qualification",
        },
        {
            "fieldname": "graduation_date_ak",
            "label":     "تاريخ التخرج",
            "fieldtype": "Date",
            "insert_after": "prev_qual_date",
        },
    ],
    # NOTE: حقول "Assessment Result" تُدار عبر regulations.ASSESSMENT_RESULT_FIELDS (مالك واحد)
}


def make_custom_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    frappe.db.commit()
    print("✓ Custom fields created.")


def _relax_course_code_unique():
    """الرموز تتكرر بين الشعب/الخطط (نفس الرمز لاسمين مختلفين) — يُلغى قيد التفرد."""
    try:
        if frappe.db.exists("Custom Field", "Course-course_code"):
            frappe.db.set_value("Custom Field", "Course-course_code", "unique", 0)
        indexes = frappe.db.sql("SHOW INDEX FROM `tabCourse`")
        names = {r[2] for r in indexes if len(r) > 4 and r[4] == "course_code"}
        for index_name in sorted(names):
            frappe.db.sql(f"ALTER TABLE `tabCourse` DROP INDEX `{index_name}`")
        frappe.db.commit()
        frappe.clear_cache()
        print("✓ course_code unique relaxed.")
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "relax_course_code_unique failed")
        raise


def ensure_national_id_unique():
    """يضمن وجود فهرس فريد على Student.national_id (لا يعتمد على سلوك migrate)."""
    if not frappe.db.exists("DocType", "Student"):
        return
    try:
        if frappe.db.get_column_index("tabStudent", "national_id", unique=True):
            return
        frappe.db.add_unique("Student", ["national_id"], constraint_name="national_id")
        frappe.db.commit()
        print("✓ national_id unique index ensured.")
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "ensure_national_id_unique failed")


# ---------------------------------------------------------------------------
# حقل الجنس في Student: قائمة «ذكر/أنثى» فقط + للقراءة فقط (يُشتق من الرقم الوطني)
# ---------------------------------------------------------------------------

GENDER_OPTIONS = "ذكر\nأنثى"
GENDER_OLD_VALUES = {"Female": "أنثى", "Male": "ذكر"}


def make_gender_field():
    # options أولاً (مع تجاهل التحقق لأن الحقل ما زال Link) ثم تحويل النوع إلى Select
    frappe.make_property_setter({
        "doctype": "Student",
        "doctype_or_field": "DocField",
        "fieldname": "gender",
        "property": "options",
        "value": GENDER_OPTIONS,
        "property_type": "Text",
    }, validate_fields_for_doctype=False)
    frappe.make_property_setter({
        "doctype": "Student",
        "doctype_or_field": "DocField",
        "fieldname": "gender",
        "property": "fieldtype",
        "value": "Select",
        "property_type": "Select",
    })
    frappe.make_property_setter({
        "doctype": "Student",
        "doctype_or_field": "DocField",
        "fieldname": "gender",
        "property": "read_only",
        "value": "1",
        "property_type": "Check",
    })

    # ترحيل القيم اللاتينية الحالية إلى العربية
    for old, new in GENDER_OLD_VALUES.items():
        frappe.db.sql(
            "update tabStudent set gender = %s where gender = %s", (new, old)
        )

    frappe.db.commit()
    print("✓ Gender field configured (ذكر/أنثى, read-only).")


# ---------------------------------------------------------------------------
# الجنسية كقائمة منسدلة (Link إلى Nationality) قابلة للإضافة
# ---------------------------------------------------------------------------

DEFAULT_NATIONALITIES = [
    "ليبي", "مصري", "تونسي", "جزائري", "مغربي",
    "سوداني", "فلسطيني", "سوري", "أردني", "أخرى",
]

NATIONALITY_LINK_DOCTYPES = ["Student", "Student Applicant", "Guardian"]

DEFAULT_BIRTH_PLACES = [
    "الخمس", "سوق الخميس", "بنغازي", "قصر الاخيار", "تاورغاء",
    "زليتن", "كعام", "صرمان", "درج", "قوقاس", "مسلاتة",
]


def make_birth_place_dropdown():
    for name in DEFAULT_BIRTH_PLACES:
        if not frappe.db.exists("Birth Place", name):
            doc = frappe.new_doc("Birth Place")
            doc.place_name = name
            doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("✓ Birth place dropdown configured.")


# ---------------------------------------------------------------------------
# التحقق الفوري من الرقم الوطني أثناء الكتابة (Client Script)
# ---------------------------------------------------------------------------

STUDENT_CLIENT_SCRIPT_NAME = "Student — الرقم الوطني: تحقق فوري"

STUDENT_CLIENT_SCRIPT = r"""
frappe.ui.form.on("Student", {
	refresh: function (frm) {
		if (frm.doc.national_id) {
			preview_national_id(frm, normalize_national_id(frm.doc.national_id));
		}
	},
	national_id: function (frm) {
		const raw = frm.doc.national_id || "";
		const nid = normalize_national_id(raw);
		if (nid !== raw) {
			frm.set_value("national_id", nid);
		}
		preview_national_id(frm, nid);
	},
	validate: function (frm) {
		const raw = frm.doc.national_id || "";
		const nid = normalize_national_id(raw);
		if (nid !== raw) {
			frm.set_value("national_id", nid);
		}
		if (nid && !preview_national_id(frm, nid)) {
			frappe.throw(__("صحّح الرقم الوطني قبل الحفظ."));
		}
	},
});

function normalize_national_id(value) {
	const arabic = "٠١٢٣٤٥٦٧٨٩";
	const persian = "۰۱۲۳۴۵۶۷۸۹";
	let out = "";
	for (const ch of value || "") {
		const a = arabic.indexOf(ch);
		const p = persian.indexOf(ch);
		if (a >= 0) {
			out += String(a);
		} else if (p >= 0) {
			out += String(p);
		} else if (/[\s\u00a0\u200b\u200e\u200f\u2010-\u2014-]/.test(ch)) {
			continue;
		} else {
			out += ch;
		}
	}
	return out;
}

function preview_national_id(frm, nid) {
	if (!nid) {
		frm.set_intro("");
		return true;
	}
	const invalid = [...new Set(nid.split("").filter((c) => !/[0-9]/.test(c)))];
	if (invalid.length) {
		frm.set_intro(
			__("لا يُسمح بالحروف أو الرموز في الرقم الوطني: «{0}».", [invalid.join("»، «")]),
			"red"
		);
		return false;
	}
	if (nid.length !== 12) {
		frm.set_intro(
			__("الرقم الوطني يجب أن يتكوّن من 12 رقماً؛ أدخلت {0} فقط.", [nid.length]),
			"orange"
		);
		return false;
	}
	if (nid[0] !== "1" && nid[0] !== "2") {
		frm.set_intro(__("الرقم الوطني يجب أن يبدأ بـ 1 (ذكر) أو 2 (أنثى)."), "red");
		return false;
	}
	const gender = nid[0] === "1" ? "ذكر" : "أنثى";
	frm.set_intro(
		__("الجنس: {0} — سنة الميلاد: {1} (تُطبَّق تلقائياً عند الحفظ).", [gender, nid.substring(1, 5)]),
		"blue"
	);
	return true;
}
"""


def make_client_script():
    """ينشئ/يحدّث Client Script للتحقق الفوري من الرقم الوطني في نموذج الطالب."""
    if not frappe.db.exists("DocType", "Student"):
        return
    if frappe.db.exists("Client Script", STUDENT_CLIENT_SCRIPT_NAME):
        doc = frappe.get_doc("Client Script", STUDENT_CLIENT_SCRIPT_NAME)
    else:
        doc = frappe.new_doc("Client Script")
        doc.name = STUDENT_CLIENT_SCRIPT_NAME
    doc.dt = "Student"
    doc.view = "Form"
    doc.enabled = 1
    doc.script = STUDENT_CLIENT_SCRIPT
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("✓ Student client script configured.")


def make_nationality_dropdown():
    for name in DEFAULT_NATIONALITIES:
        if not frappe.db.exists("Nationality", name):
            doc = frappe.new_doc("Nationality")
            doc.nationality_name = name
            doc.insert(ignore_permissions=True)

    for dt in NATIONALITY_LINK_DOCTYPES:
        if not frappe.db.exists("DocType", dt):
            continue
        # options أولاً حتى يجتاز التحقق عند تحويل النوع إلى Link
        frappe.make_property_setter({
            "doctype": dt,
            "doctype_or_field": "DocField",
            "fieldname": "nationality",
            "property": "options",
            "value": "Nationality",
            "property_type": "Text",
        }, validate_fields_for_doctype=False)
        frappe.make_property_setter({
            "doctype": dt,
            "doctype_or_field": "DocField",
            "fieldname": "nationality",
            "property": "fieldtype",
            "value": "Link",
            "property_type": "Select",
        })

    frappe.db.commit()
    print("✓ Nationality dropdown configured.")


# ---------------------------------------------------------------------------
# Course + Program data
# ---------------------------------------------------------------------------

COURSES = [
    # الفصل الأول العام
    ("رياضة I",                              "GS111", 3, 2, 0, 1, 1),
    ("فيزياء",                               "GS112", 4, 2, 0, 2, 1),
    ("لغة إنجليزية I",                       "GH113", 2, 2, 0, 0, 1),
    ("اللغة العربية والدراسات الإسلامية",    "GH114", 2, 2, 0, 0, 1),
    ("أساسيات الحاسب الآلي",                 "GS115", 3, 2, 2, 0, 1),
    ("صحة وسلامة مهنية",                     "GS119", 2, 2, 0, 0, 1),
    ("أسس هندسة كهربائية",                   "EE117", 4, 3, 2, 0, 1),
    ("أساسيات البرمجة",                       "GS116", 3, 2, 2, 0, 1),
    # مشتركة
    ("لغة إنجليزية II",                      "GH123", 2, 2, 0, 0, 0),
    ("رياضة II",                             "GS122", 3, 3, 0, 0, 0),
    ("برمجة بلغة ++C",                       "CP121", 4, 2, 4, 0, 0),
    ("أساسيات الشبكات (CCNA1)",              "CN127", 4, 2, 3, 0, 0),
    ("قواعد بيانات I",                       "CD121", 4, 3, 2, 0, 0),
    ("لغة إنجليزية III",                     "GH231", 2, 2, 0, 0, 0),
    ("البرمجة الشيئية",                       "CP231", 4, 2, 4, 0, 0),
    ("قواعد بيانات II",                      "CD231", 4, 2, 2, 0, 0),
    ("تحليل وتصميم نظم",                     "CP233", 3, 3, 2, 0, 0),
    ("لغة إنجليزية IV",                      "GH241", 2, 2, 0, 0, 0),
    ("منهجية البحث",                          "GS251", 2, 2, 0, 0, 0),
    ("تراكيب البيانات والخوارزميات",          "CP242", 4, 2, 3, 0, 0),
    ("إدارة مشاريع",                          "CN247", 2, 2, 0, 0, 0),
    ("نظم تشغيل شبكات",                      "CN232", 4, 2, 4, 0, 0),
    ("متطلبات حماية الشبكات",                "CN242", 4, 2, 3, 0, 0),
    # قواعد البيانات
    ("مقدمة في برمجة الإنترنت",              "CW121", 4, 2, 3, 0, 0),
    ("إحصاء واحتمالات",                       "GS248", 3, 3, 0, 0, 0),
    ("واجهات رسومية I",                      "CW231", 4, 2, 4, 0, 0),
    ("تطبيقات ويب I",                        "CW243", 4, 2, 4, 0, 0),
    ("أنظمة قواعد البيانات المتقدمة",        "CD241", 4, 2, 3, 0, 0),
    ("البرمجة بتقنية DBMS",                  "CD242", 4, 2, 4, 0, 0),
    ("XML Programming",                       "CW351", 4, 3, 2, 0, 0),
    ("أساسيات مستودعات البيانات",            "CD351", 4, 3, 2, 0, 0),
    ("الإدارة بتقنية DBMS",                  "CD352", 4, 2, 4, 0, 0),
    ("أمن وحماية المعلومات",                 "CW244", 3, 2, 2, 0, 0),
    # تقنية المعلومات
    ("أنظمة رقمية",                           "CI121", 4, 3, 2, 0, 0),
    ("البرمجة المرئية I",                    "CI231", 4, 2, 3, 0, 0),
    ("تطبيقات حاسوب II",                     "CI232", 3, 1, 3, 0, 0),
    ("البرمجة المرئية II",                   "CI241", 4, 2, 3, 0, 0),
    ("تقنية ADO.NET",                         "CI242", 4, 2, 3, 0, 0),
    ("هندسة برمجيات",                         "CP243", 3, 2, 2, 0, 0),
    ("الدعم الفني لتقنية المعلومات",          "CI351", 4, 3, 2, 0, 0),
    ("مصطلحات فنية",                          "CI352", 2, 2, 0, 0, 0),
    ("وسائط متعددة",                          "CP351", 4, 2, 3, 0, 0),
    # الشبكات
    ("تراكيب منفصلة",                         "CP122", 2, 2, 0, 0, 0),
    ("التصميم الرقمي والمنطقي",              "CP123", 4, 2, 3, 0, 0),
    ("نظم تشغيل الحاسبات",                   "CP241", 4, 2, 3, 0, 0),
    ("اتصالات البيانات",                      "CN233", 4, 3, 1, 0, 0),
    ("تشبيك شبكات",                           "CN234", 2, 1, 1, 0, 0),
    ("الشبكة العنكبوتية",                     "CN235", 4, 3, 1, 0, 0),
    ("بنية وتنظيم حاسبات",                   "CN236", 3, 3, 0, 0, 0),
    ("CCNA2 Routing and Switching",           "CN237", 4, 3, 2, 0, 0),
    ("الشبكات اللاسلكية",                     "CN244", 4, 3, 2, 0, 0),
    ("إدارة الشبكات",                         "CN246", 4, 3, 2, 0, 0),
    ("Scaling Network",                        "CN243", 4, 3, 2, 0, 0),
    ("منهجيات بحث",                           "GS357", 2, 2, 0, 0, 0),
    ("نظم تأمين شبكات",                       "CN352", 4, 3, 2, 0, 0),
    ("برمجة شبكات",                           "CN353", 4, 3, 2, 0, 0),
    ("CCNA4 Connecting Networks (WAN)",        "CN354", 4, 3, 2, 0, 0),
    ("Voice over IP",                          "CN355", 4, 3, 2, 0, 0),
    # موحّدة
    ("مواضيع مختارة 1",                       "CD353", 4, 3, 2, 0, 0),
    ("مواضيع مختارة 2",                       "CD363", 4, 2, 4, 0, 0),
    ("تدريب ميداني",                          "CD361", 3, 0, 4, 0, 0),
    ("مشروع تخرج",                            "CD362", 4, 0, 4, 0, 0),
]

ALT_CODES = {
    "مواضيع مختارة 1": [("CI353", "بديل"), ("CN351", "بديل")],
    "مواضيع مختارة 2": [("CI363", "بديل"), ("CN363", "بديل")],
    "تدريب ميداني":    [("CI361", "بديل"), ("CN361", "بديل")],
    "مشروع تخرج":     [("CI362", "بديل"), ("CN362", "بديل")],
}

# (semester, course_name, [(prereq_name, prereq_type), ...])
PROGRAM_COURSES = {
    "قواعد البيانات": [
        (2, "لغة إنجليزية II",             [("لغة إنجليزية I", "إلزامي")]),
        (2, "رياضة II",                    [("رياضة I", "إلزامي")]),
        (2, "برمجة بلغة ++C",             [("أساسيات البرمجة", "إلزامي")]),
        (2, "أساسيات الشبكات (CCNA1)",    []),
        (2, "مقدمة في برمجة الإنترنت",    [("أساسيات البرمجة", "إلزامي")]),
        (2, "قواعد بيانات I",             []),
        (3, "لغة إنجليزية III",           [("لغة إنجليزية II", "إلزامي")]),
        (3, "البرمجة الشيئية",            [("برمجة بلغة ++C", "إلزامي")]),
        (3, "قواعد بيانات II",            [("قواعد بيانات I", "إلزامي")]),
        (3, "تحليل وتصميم نظم",           []),
        (3, "إحصاء واحتمالات",            []),
        (3, "واجهات رسومية I",            []),
        (3, "تطبيقات ويب I",              [("مقدمة في برمجة الإنترنت", "إلزامي")]),
        (4, "لغة إنجليزية IV",            [("لغة إنجليزية III", "إلزامي")]),
        (4, "أنظمة قواعد البيانات المتقدمة", [("قواعد بيانات II", "إلزامي")]),
        (4, "البرمجة بتقنية DBMS",        [("قواعد بيانات II", "إلزامي")]),
        (4, "منهجية البحث",                []),
        (4, "تراكيب البيانات والخوارزميات", [("برمجة بلغة ++C", "إلزامي")]),
        (4, "نظم تشغيل شبكات",            []),
        (4, "XML Programming",            [("مقدمة في برمجة الإنترنت", "إلزامي")]),
        (5, "إدارة مشاريع",               []),
        (5, "أساسيات مستودعات البيانات",  [("أنظمة قواعد البيانات المتقدمة", "إلزامي")]),
        (5, "الإدارة بتقنية DBMS",        [("البرمجة بتقنية DBMS", "إلزامي")]),
        (5, "أمن وحماية المعلومات",       []),
        (5, "مواضيع مختارة 1",            []),
        (5, "تقنية ADO.NET",              []),
        (6, "تدريب ميداني",               []),
        (6, "مشروع تخرج",                 []),
        (6, "مواضيع مختارة 2",            []),
    ],
    "تقنية المعلومات": [
        (2, "لغة إنجليزية II",            [("لغة إنجليزية I", "إلزامي")]),
        (2, "رياضة II",                   [("رياضة I", "إلزامي")]),
        (2, "برمجة بلغة ++C",            [("أساسيات البرمجة", "إلزامي")]),
        (2, "أساسيات الشبكات (CCNA1)",   []),
        (2, "قواعد بيانات I",            []),
        (2, "أنظمة رقمية",               [("أساسيات الحاسب الآلي", "إلزامي")]),
        (3, "لغة إنجليزية III",          [("لغة إنجليزية II", "إلزامي")]),
        (3, "قواعد بيانات II",           [("قواعد بيانات I", "إلزامي")]),
        (3, "تحليل وتصميم نظم",          []),
        (3, "البرمجة المرئية I",          []),
        (3, "متطلبات حماية الشبكات",     [("أساسيات الشبكات (CCNA1)", "إلزامي")]),
        (3, "تطبيقات حاسوب II",          []),
        (3, "البرمجة الشيئية",           [("برمجة بلغة ++C", "إلزامي")]),
        (4, "لغة إنجليزية IV",           [("لغة إنجليزية III", "إلزامي")]),
        (4, "البرمجة المرئية II",         [("البرمجة المرئية I", "إلزامي")]),
        (4, "تقنية ADO.NET",             []),
        (4, "مقدمة في برمجة الإنترنت",   []),
        (4, "هندسة برمجيات",             []),
        (4, "تراكيب البيانات والخوارزميات", [("برمجة بلغة ++C", "إلزامي")]),
        (4, "منهجية البحث",               []),
        (5, "إدارة مشاريع",              []),
        (5, "الدعم الفني لتقنية المعلومات", []),
        (5, "XML Programming",           []),
        (5, "مصطلحات فنية",              []),
        (5, "مواضيع مختارة 1",           []),
        (5, "وسائط متعددة",              []),
        (6, "تدريب ميداني",              []),
        (6, "مشروع تخرج",               []),
        (6, "مواضيع مختارة 2",           []),
    ],
    "الشبكات": [
        (2, "لغة إنجليزية II",           [("لغة إنجليزية I", "إلزامي")]),
        (2, "رياضة II",                  [("رياضة I", "إلزامي")]),
        (2, "برمجة بلغة ++C",           [("أساسيات البرمجة", "إلزامي")]),
        (2, "أساسيات الشبكات (CCNA1)",  []),
        (2, "تراكيب منفصلة",             []),
        (2, "التصميم الرقمي والمنطقي",   []),
        (2, "نظم تشغيل الحاسبات",       []),
        (3, "لغة إنجليزية III",          [("لغة إنجليزية II", "إلزامي")]),
        (3, "اتصالات البيانات",          []),
        (3, "نظم تشغيل شبكات",           []),
        (3, "تشبيك شبكات",              []),
        (3, "الشبكة العنكبوتية",         []),
        (3, "بنية وتنظيم حاسبات",        []),
        (3, "CCNA2 Routing and Switching", [("أساسيات الشبكات (CCNA1)", "إلزامي")]),
        (4, "لغة إنجليزية IV",           [("لغة إنجليزية III", "إلزامي")]),
        (4, "متطلبات حماية الشبكات",     []),
        (4, "الشبكات اللاسلكية",         []),
        (4, "إدارة الشبكات",             []),
        (4, "قواعد بيانات I",            []),
        (4, "Scaling Network",           [("CCNA2 Routing and Switching", "إلزامي")]),
        (5, "منهجيات بحث",              []),
        (5, "مواضيع مختارة 1",          []),
        (5, "نظم تأمين شبكات",          []),
        (5, "برمجة شبكات",              []),
        (5, "CCNA4 Connecting Networks (WAN)", []),
        (5, "Voice over IP",            []),
        (6, "تدريب ميداني",             []),
        (6, "مشروع تخرج",              []),
        (6, "مواضيع مختارة 2",         []),
    ],
}

ACADEMIC_YEAR = "2025-2026"
TERMS        = [("خريف 2025", "2025-09-01", "2026-01-31"), ("ربيع 2026", "2026-02-01", "2026-08-31")]
DEPT_PARENT  = "المعهد العالي للعلوم والتقنية - الخمس"
DEPARTMENT   = "تقنيات الحاسوب"


# ---------------------------------------------------------------------------
# seed helpers
# ---------------------------------------------------------------------------

def _ensure_academic():
    if not frappe.db.exists("Academic Year", ACADEMIC_YEAR):
        frappe.get_doc({
            "doctype": "Academic Year",
            "academic_year_name": ACADEMIC_YEAR,
            "year_start_date": "2025-09-01",
            "year_end_date":   "2026-08-31",
        }).insert(ignore_permissions=True)
    for title, start, end in TERMS:
        if frappe.db.exists("Academic Term", {"term_name": title, "academic_year": ACADEMIC_YEAR}):
            continue
        frappe.get_doc({
            "doctype": "Academic Term", "term_name": title,
            "academic_year": ACADEMIC_YEAR,
            "term_start_date": start, "term_end_date": end,
        }).insert(ignore_permissions=True)


def _ensure_department_doc(name, company, is_group, parent=None):
    """يُعيد اسم Department موجود (بالبحث عن department_name) أو ينشئه."""
    existing = frappe.db.get_value("Department", {"department_name": name})
    if existing:
        return existing
    doc = frappe.new_doc("Department")
    doc.department_name = name
    doc.company = company
    doc.is_group = is_group
    if parent:
        doc.parent_department = parent
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_department():
    company = (
        frappe.db.get_value("Company", {"name": DEPT_PARENT}, "name")
        or frappe.defaults.get_defaults().company
        or frappe.db.get_value("Company", {}, "name")
    )
    parent_name = _ensure_department_doc(DEPT_PARENT, company, is_group=1)
    for title in [DEPARTMENT] + plans_data.NEW_DEPARTMENTS:
        _ensure_department_doc(title, company, is_group=0, parent=parent_name)


def _department_docname(dept_title):
    """اسم Department الفعلي (قد يلحق به اختصار الشركة) للربط الصحيح."""
    return frappe.db.get_value("Department", {"department_name": dept_title}) or dept_title


def _department_name():
    return _department_docname(DEPARTMENT)


def _ensure_programs():
    for prog, dept_title in plans_data.PROGRAM_DEPARTMENT.items():
        department = _department_docname(dept_title)
        if not frappe.db.exists("Program", prog):
            frappe.get_doc({
                "doctype": "Program", "program_name": prog, "department": department,
            }).insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Program", prog, "department", department)
    for prog in PROGRAM_COURSES:
        if prog in plans_data.PROGRAM_DEPARTMENT:
            continue
        if not frappe.db.exists("Program", prog):
            frappe.get_doc({
                "doctype": "Program", "program_name": prog, "department": _department_name(),
            }).insert(ignore_permissions=True)


def _ensure_courses():
    department = _department_name()
    for name, code, units, th, pr, tut, general in COURSES:
        doc = frappe.get_doc("Course", name) if frappe.db.exists("Course", name) else frappe.new_doc("Course")
        doc.course_name    = name
        doc.course_code    = code
        doc.units          = units
        doc.theory_hours   = th
        doc.practical_hours = pr
        doc.tutorial_hours = tut
        doc.is_general     = general
        doc.department     = department
        doc.course_codes   = []
        doc.append("course_codes", {"code": code, "code_type": "أساسي", "academic_year": ACADEMIC_YEAR})
        for alt, typ in ALT_CODES.get(name, []):
            doc.append("course_codes", {"code": alt, "code_type": typ, "academic_year": ACADEMIC_YEAR})
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)

    for name, code, units, th, pr, tut, general, dept_title, alts in plans_data.NEW_COURSES:
        doc = frappe.get_doc("Course", name) if frappe.db.exists("Course", name) else frappe.new_doc("Course")
        doc.course_name    = name
        doc.course_code    = code
        doc.units          = units
        doc.theory_hours   = th
        doc.practical_hours = pr
        doc.tutorial_hours = tut
        doc.is_general     = general
        doc.department     = _department_docname(dept_title)
        doc.course_codes   = []
        doc.append("course_codes", {"code": code, "code_type": "أساسي", "academic_year": ACADEMIC_YEAR})
        for alt, typ in alts:
            doc.append("course_codes", {"code": alt, "code_type": typ, "academic_year": ACADEMIC_YEAR})
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)


def _apply_db_course_updates():
    """تحديث مقررات قائمة: تفعيل «مادة عامة» + إضافة الرموز البديلة دون تكرار."""
    for name, general in plans_data.DB_GENERAL_UPDATES.items():
        if not frappe.db.exists("Course", name):
            continue
        doc = frappe.get_doc("Course", name)
        if general:
            doc.is_general = 1
        existing = {r.code for r in doc.course_codes}
        for alt in plans_data.DB_ALT_CODES.get(name, []):
            if alt not in existing:
                doc.append("course_codes", {"code": alt, "code_type": "بديل", "academic_year": ACADEMIC_YEAR})
        doc.save(ignore_permissions=True)


def _ensure_program_courses():
    for prog, rows in PROGRAM_COURSES.items():
        doc = frappe.get_doc("Program", prog)
        doc.courses = []
        doc.prerequisites = []
        for cname in plans_data.COMPUTER_SEM1:
            if frappe.db.exists("Course", cname):
                doc.append("courses", {"course": cname, "course_name": cname, "required": 1, "semester": 1})
        for sem, cname, prereqs in rows:
            if not frappe.db.exists("Course", cname):
                frappe.throw(f"Course not found: {cname}")
            row = {"course": cname, "course_name": cname, "required": 1, "semester": sem}
            mandatory = [p for p, t in prereqs if t == "إلزامي"]
            if mandatory:
                row["prerequisite_course"] = mandatory[0]
            doc.append("courses", row)
            # جدول المتطلبات على مستوى البرنامج (لأن الجداول لا تُدمج داخل الجداول)
            for p, t in prereqs:
                doc.append("prerequisites", {
                    "course": cname,
                    "prerequisite_course": p,
                    "prerequisite_type": t,
                })
        doc.save(ignore_permissions=True)

    for prog, rows in plans_data.NEW_PROGRAM_COURSES.items():
        doc = frappe.get_doc("Program", prog)
        doc.courses = []
        doc.prerequisites = []
        for sem, cname, prereqs in rows:
            if not frappe.db.exists("Course", cname):
                frappe.throw(f"Course not found: {cname}")
            row = {"course": cname, "course_name": cname, "required": 1, "semester": sem}
            if prereqs:
                row["prerequisite_course"] = prereqs[0]
            doc.append("courses", row)
            for p in prereqs:
                doc.append("prerequisites", {
                    "course": cname,
                    "prerequisite_course": p,
                    "prerequisite_type": "إلزامي",
                })
        doc.save(ignore_permissions=True)


PRINT_FORMAT_FILES = [
    ("بطاقة الطالب الدراسية", "Student", "student_card.html"),
    ("كشف الدرجات", "Student", "transcript.html"),
    ("إشعار النتيجة الفصلي", "Student Semester Result", "semester_notice.html"),
    ("نموذج النتيجة", "Student", "final_result.html"),
    ("كشف أسماء الطلبة", "Student Group", "student_group_list.html"),
]


def make_print_formats():
    """يُنشئ قوالب الطباعة الرسمية (Jinja) مرة واحدة فقط.

    بعد الإنشاء، السجلات في القاعدة هي المصدر الوحيد —
    أي تعديل يجريه المستخدم من الواجهة (Print Format) يبقى دائماً
    ولا يُستبدل بالملفات.
    """
    import os

    base = os.path.join(frappe.get_app_path("al_khoms_edu"), "templates", "print_formats")
    created = skipped = 0
    for name, doc_type, filename in PRINT_FORMAT_FILES:
        if frappe.db.exists("Print Format", name):
            skipped += 1
            continue
        with open(os.path.join(base, filename), encoding="utf-8") as fh:
            html = fh.read()
        pf = frappe.new_doc("Print Format")
        pf.name = name
        pf.doc_type = doc_type
        pf.print_format_type = "Jinja"
        pf.custom_format = 1
        pf.html = html
        pf.insert(ignore_permissions=True)
        created += 1
    frappe.db.commit()
    print(f"✓ Print formats → created: {created} | existing (skipped): {skipped}")
    return {"created": created, "skipped": skipped}


def run():
    make_custom_fields()
    _relax_course_code_unique()
    ensure_national_id_unique()
    make_gender_field()
    make_nationality_dropdown()
    make_birth_place_dropdown()
    make_client_script()
    _ensure_academic()
    _ensure_department()
    _ensure_programs()
    _ensure_courses()
    _apply_db_course_updates()
    _ensure_program_courses()
    make_print_formats()
    frappe.db.commit()
    print("✓ Pilot structure created successfully.")
