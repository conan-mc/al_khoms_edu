# -*- coding: utf-8 -*-
app_name = "al_khoms_edu"
app_title = "Al Khoms Education Institute"
app_publisher = "Al Khoms Higher Institute of Science and Technology"
app_description = "Customizations for the Higher Institute of Science and Technology"
app_email = "info@alkhoms.edu.ly"
app_license = "mit"

# تطبيقات لا يعمل التطبيق دونها (تُثبَّت قبل al_khoms_edu)
required_apps = ["erpnext", "education", "pos_next"]

# Jinja – دوال قوالب الطباعة الرسمية
jinja = {
	"methods": [
		"al_khoms_edu.print_helpers.card_context",
		"al_khoms_edu.print_helpers.transcript_context",
		"al_khoms_edu.print_helpers.notice_context",
		"al_khoms_edu.print_helpers.final_result_context",
		"al_khoms_edu.print_helpers.fmt",
		# التحقق الإلكتروني: رمز QR + رابط صفحة التحقق العامة
		"al_khoms_edu.verification.verify_qr",
		"al_khoms_edu.verification.verify_url",
	]
}

# الصفحة الافتراضية لكل دور عند تسجيل الدخول
on_session_creation = ["al_khoms_edu.landing.apply_role_landing"]

# Document Events – trigger academic logic
doc_events = {
	"Assessment Result": {
		"before_validate": "al_khoms_edu.regulations.prepare_assessment_result",
		"validate": "al_khoms_edu.regulations.validate_assessment_result",
		# المحاولات تُسجَّل عند الاعتماد فقط، لا عند إنشاء المسودة
		"on_submit": "al_khoms_edu.academic_engine.after_assessment_submit",
	},
	"Course Enrollment": {
		"before_save": [
			"al_khoms_edu.academic_engine.before_course_enrollment_save",
			"al_khoms_edu.regulations.validate_course_enrollment",
		],
	},
	"Student": {
		# قبل validate حتى يُشتق الجنس من الرقم الوطني قبل إنشاء المستخدم
		"before_validate": [
			"al_khoms_edu.validators.validate_national_id",
		],
		"validate": [
			"al_khoms_edu.regulations.validate_student",
		],
	},
	"Program Enrollment": {
		"validate": "al_khoms_edu.regulations.validate_program_enrollment",
	},
}

# بعد تركيب التطبيق: الحقول المخصصة + سياسة Phase 1
after_install = "al_khoms_edu.regulations.after_install"

# بعد كل migrate: ضمان وصول الحقول المخصصة الجديدة للسايتات القائمة (idempotent)
after_migrate = "al_khoms_edu.regulations.after_migrate"

# ---------------------------------------------------------------------------
# Fixtures — مالك واحد لكل سجل (Code XOR Fixtures)
#   • Custom Field: الحقول المُنشأة من الواجهة فقط (is_system_generated=0).
#     حقول الكود (is_system_generated=1) يملكها الكود عبر install_custom_fields.
#   • Custom DocPerm: صلاحيات المستخدم، باستثناء أدوار POS التي يملكها pos_next.
#   • Property Setter / Print Format: التخصيصات الظاهرة (idempotent بالاسم).
#   • لا نُصدّر Workspace/Dashboard/Notification (قياسية) ولا Client Script (ينشئه seed).
# ---------------------------------------------------------------------------
fixtures = [
	{"dt": "Custom Field", "filters": [["is_system_generated", "=", 0]]},
	{
		"dt": "Custom DocPerm",
		"filters": [["role", "not in", ["POSNext Cashier", "Nexus POS Manager"]]],
	},
	{"dt": "Property Setter"},
	{"dt": "Print Format", "filters": [["standard", "=", "No"]]},
]

# Scheduled Tasks
scheduler_events = {
	"weekly": [
		"al_khoms_edu.academic_engine.weekly_promotion_evaluation",
	]
}
