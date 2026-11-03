# -*- coding: utf-8 -*-
"""ترحيل شامل لبيانات المعهد من قاعدة Access (pp_data.MDB).

يغطي جميع الأقسام (وليس قسم الحاسوب فقط) ويشمل صفوف «عام» التي كانت
السكربتات السابقة تُسقطها.

المراحل (كل مرحلة قابلة للتكرار — idempotent):
  1. ensure_courses      : إنشاء المواد الناقصة من جدول subject
  2. ensure_years        : السنوات والفصول الدراسية
  3. create_students     : الطلاب مع الرقم القديم والبيانات الشخصية
  4. enroll              : Program Enrollment + Course Enrollment
  5. results             : Assessment Plan + Assessment Result

الاستخدام:
    bench --site erp.local execute al_khoms_edu.migrate_all.preflight
    bench --site erp.local execute al_khoms_edu.migrate_all.run --kwargs "{'depts':['التحكم الآلي']}"
    bench --site erp.local execute al_khoms_edu.migrate_all.run
"""

import re
from collections import Counter, defaultdict

import frappe

from al_khoms_edu.access_migrate_academic import (
	ASSESSMENT_GROUP,
	CRITERIA,
	GRADE_SCALE,
	MAX_SCORE,
	_ensure_assessment_plan,
	_ensure_student_group,
	grade_letter,
	normalize_year,
	term_name_for,
)
from al_khoms_edu.access_migrate_computer import time_to_term_name

SOURCE = "/home/frappe/Documents/pp_data.MDB"

# dept_type في Access → اسم برنامج Frappe
DEPT_TO_PROGRAM = {
	"قواعد البيانات": "قواعد البيانات",
	"تقنية معلومات": "تقنية المعلومات",
	"الشبكات": "الشبكات",
	"ميكانيكا القوى": "القوى الميكانيكية",
	"قوى": "القوى الميكانيكية",
	"تبريد وتكييف": "التبريد والتكييف",
	"التحكم الآلي": "التحكم الآلي",
	"أنظمة القدرة": "أنظمة القدرة",
	"التقنية الكيميائية": "التقنية الكيميائية",
	"الإنشاءات": "الإنشاءات",
	"تصميم معماري": "المعمارية",
	"وقاية نبات": "وقاية النبات",
}

GENERAL_PROGRAM = "الفصل العام"

# رموز قديمة بنفس مادة موجودة (اختلاف ترتيب/كتابة الرمز)
CODE_ALIASES = {
	"CP128": "CP121",
	"CP124": "CP122",
	"CP125": "CP123",
	"CP126": "CP241",
	"CW126": "CW121",
	"CW129": "CD121",
	"CW246": "CW243",
	"CP232": "البرمجة الشيئية",
	"CP234": "تحليل وتصميم نظم",
	"CP244": "تراكيب البيانات والخوارزميات",
	"CP1126": "نظم تشغيل الحاسبات",
	"CD233": "قواعد بيانات II",
	"CD243": "البرمجة بتقنية DBMS",
}

GENDER_MAP = {"ذكر": "ذكر", "انثى": "أنثى", "أنثى": "أنثى", "male": "ذكر", "female": "أنثى"}

BAD_CITIES = {"ليبية", "ليبي", "ليـبـــــي", "ليبيه"}

_TABLES = {}
_PARSER = None


# ---------------------------------------------------------------------------
# قراءة Access
# ---------------------------------------------------------------------------

def _parser():
	global _PARSER
	if _PARSER is None:
		from access_parser import AccessParser
		from access_parser.access_parser import AccessTable

		if not getattr(AccessTable._parse_dynamic_length_data, "_ak_patched", False):
			original = AccessTable._parse_dynamic_length_data

			def patched(self, record, rrm, rrcm, null_table):
				return original(self, record, rrm, rrcm, list(null_table) + [False] * 128)

			patched._ak_patched = True
			AccessTable._parse_dynamic_length_data = patched

		_PARSER = AccessParser(SOURCE)
	return _PARSER


def tx(value):
	"""فكّ ترميز قيم Access (cp1256 مخزّنة كـ latin-1)."""
	if value is None:
		return ""
	if isinstance(value, (int, float)):
		return value
	if isinstance(value, bytes):
		try:
			return value.decode("cp1256").strip()
		except Exception:
			return value.decode("latin-1", "ignore").strip()
	text = str(value)
	try:
		return text.encode("latin-1").decode("cp1256").strip()
	except Exception:
		return text.strip()


def rows(table):
	"""جدول Access كقائمة قواميس بترميز سليم (مع تخزين مؤقت)."""
	if table in _TABLES:
		return _TABLES[table]
	data = _parser().get_table(table).parse()
	keys = list(data.keys())
	n = len(data[keys[0]]) if keys else 0
	out = [{k: tx(data[k][i]) for k in keys} for i in range(n)]
	_TABLES[table] = out
	return out


def _num(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _date(value):
	text = str(value or "")
	m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
	if m and 1900 <= int(m.group(1)) <= 2100:
		return m.group(0)
	return None


# ---------------------------------------------------------------------------
# خريطة الطالب → البرنامج
# ---------------------------------------------------------------------------

def student_roster():
	"""يمنح كل طالب في جدول degree برنامجًا واحدًا.

	الأولوية: أكثر dept_type تخصصًا في صفوفه ← dept_type في student_data
	← برنامج «الفصل العام» (طالب سنة أولى لم يتخصص بعد).
	"""
	personal = {}
	for r in rows("student_data"):
		sid = str(r.get("stud_number") or "").strip()
		if sid and sid not in personal:
			personal[sid] = r

	votes = defaultdict(Counter)
	all_students = set()
	for r in rows("degree"):
		sid = str(r.get("stud_number") or "").strip()
		if not sid:
			continue
		all_students.add(sid)
		dept = str(r.get("dept_type") or "").strip()
		if dept and dept != "عام" and dept in DEPT_TO_PROGRAM:
			votes[sid][DEPT_TO_PROGRAM[dept]] += 1

	roster = {}
	for sid in all_students:
		program = None
		if votes[sid]:
			program = votes[sid].most_common(1)[0][0]
		if not program:
			dept = str(personal.get(sid, {}).get("dept_type") or "").strip()
			program = DEPT_TO_PROGRAM.get(dept)
		source = "specialization" if votes[sid] else ("student_data" if program else "general")
		roster[sid] = {
			"program": program or GENERAL_PROGRAM,
			"source": source,
			"personal": personal.get(sid, {}),
		}
	return roster


# ---------------------------------------------------------------------------
# المواد
# ---------------------------------------------------------------------------

def _course_index():
	m = {}
	for c in frappe.get_all("Course", fields=["name", "course_code", "units"]):
		if c.course_code:
			m[str(c.course_code).upper().replace(" ", "")] = c
	for ac in frappe.get_all("Course Alternate Code", fields=["parent", "code"]):
		if ac.code:
			m.setdefault(str(ac.code).upper().replace(" ", ""), {"name": ac.parent})
	return m


def _subject_index():
	m = {}
	for r in rows("subject"):
		code = str(r.get("sub_no") or "").upper().replace(" ", "")
		if not code or code in m:
			continue
		m[code] = {
			"name": str(r.get("arabic") or "").strip(),
			"units": int(_num(r.get("unit")) or 0),
		}
	return m


def ensure_courses():
	"""إنشاء المواد الناقصة اعتمادًا على جدول subject (الاسم والوحدات)."""
	courses = _course_index()
	subjects = _subject_index()
	needed = set()
	for r in rows("degree"):
		for i in range(1, 14):
			code = str(r.get(f"sub_no{i}") or "").upper().replace(" ", "").strip()
			if code and code != "0":
				needed.add(code)

	created, linked, skipped = 0, 0, []
	for code in sorted(needed):
		target = CODE_ALIASES.get(code)
		if target and frappe.db.exists("Course", target):
			if code not in courses:
				doc = frappe.get_doc("Course", target)
				doc.append("course_codes", {"code": code, "code_type": "بديل"})
				doc.save(ignore_permissions=True)
				courses[code] = {"name": target}
				linked += 1
			continue
		if code in courses:
			continue
		info = subjects.get(code)
		if not info or not info["name"]:
			skipped.append(code)
			continue
		name = info["name"]
		if frappe.db.exists("Course", name):
			doc = frappe.get_doc("Course", name)
			if not any(str(x.code).upper().replace(" ", "") == code for x in doc.course_codes):
				doc.append("course_codes", {"code": code, "code_type": "بديل"})
				doc.save(ignore_permissions=True)
			courses[code] = {"name": name}
			linked += 1
			continue
		doc = frappe.new_doc("Course")
		doc.course_name = name
		doc.course_code = code
		doc.units = info["units"] or 0
		doc.insert(ignore_permissions=True)
		courses[code] = {"name": name}
		created += 1
	frappe.db.commit()
	print(f"courses created: {created} | aliases linked: {linked} | no name in subject: {skipped or 'none'}")
	return {"created": created, "linked": linked, "skipped": skipped}


def ensure_general_program():
	"""برنامج «الفصل العام» لطلاب السنة الأولى غير المتخصصين."""
	if frappe.db.exists("Program", GENERAL_PROGRAM):
		return GENERAL_PROGRAM
	doc = frappe.new_doc("Program")
	doc.program_name = GENERAL_PROGRAM
	doc.department = frappe.db.get_value("Department", {"department_name": "تقنيات الحاسوب"}, "name")
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print("created program:", GENERAL_PROGRAM)
	return GENERAL_PROGRAM


# ---------------------------------------------------------------------------
# السنوات والفصول
# ---------------------------------------------------------------------------

def ensure_years():
	years = set()
	for r in rows("degree"):
		ay = normalize_year(r.get("yr_no"))
		if ay:
			years.add(ay)
	created_y = created_t = 0
	for ay in sorted(years):
		end, start = ay.split("/")
		if not (end.isdigit() and start.isdigit()) or not (0 < int(end) - int(start) <= 1):
			print("  !! invalid academic year skipped:", ay)
			continue
		if not frappe.db.exists("Academic Year", ay):
			doc = frappe.new_doc("Academic Year")
			doc.academic_year_name = ay
			doc.year_start_date = f"{start}-09-01"
			doc.year_end_date = f"{end}-06-30"
			doc.insert(ignore_permissions=True)
			created_y += 1
		for term_ar, s, e in (
			("خريف", f"{start}-09-01", f"{start}-12-31"),
			("ربيع", f"{end}-01-15", f"{end}-05-31"),
		):
			name = term_name_for(ay, term_ar)
			if frappe.db.exists("Academic Term", name):
				continue
			doc = frappe.new_doc("Academic Term")
			doc.academic_year = ay
			doc.term_name = name
			doc.term_start_date = s
			doc.term_end_date = e
			doc.insert(ignore_permissions=True)
			created_t += 1
	frappe.db.commit()
	print(f"years: {len(years)} (created {created_y}) | terms created: {created_t}")
	return {"years": len(years), "created_years": created_y, "created_terms": created_t}


# ---------------------------------------------------------------------------
# الطلاب
# ---------------------------------------------------------------------------

def _used_national_ids():
	rows_ = frappe.db.sql("select national_id from tabStudent where ifnull(national_id,'')!=''")
	return {r[0] for r in rows_}


def _new_national_id(gender, dob, used, seq):
	digit = "1" if gender == "ذكر" else "2"
	year = 2000
	if dob and len(dob) >= 4 and dob[:4].isdigit():
		year = int(dob[:4])
		if not (1900 <= year <= 2100):
			year = 2000
	while True:
		nid = f"{digit}{year:04d}999{seq[0]:04d}"
		seq[0] += 1
		if nid not in used:
			used.add(nid)
			return nid


def create_students(programs=None, limit=None):
	# تعطيل إنشاء Customer تلقائيًا: اسم العميل = اسم الطالب، والأسماء المتكررة
	# تُسبب DuplicateEntryError. سجلات الطلاب الأكاديمية لا تحتاج عميلاً.
	try:
		from education.education.doctype.student.student import Student as EduStudent

		_orig_customer = EduStudent.set_missing_customer_details
		EduStudent.set_missing_customer_details = lambda self: None
	except Exception as exc:  # noqa: BLE001
		print("  !! customer auto-create NOT disabled:", exc)
		_orig_customer = None
	roster = student_roster()
	existing = {
		str(s.legacy_student_number): s.name
		for s in frappe.get_all("Student", fields=["name", "legacy_student_number"])
		if s.legacy_student_number
	}
	emails = {
		e.student_email_id
		for e in frappe.get_all("Student", fields=["student_email_id"])
		if e.student_email_id
	}
	used_nid = _used_national_ids()
	seq = [1]

	targets = [
		(sid, info)
		for sid, info in roster.items()
		if not programs or info["program"] in programs
	]
	if limit:
		targets = targets[:limit]

	created = skipped = 0
	for sid, info in targets:
		if sid in existing:
			skipped += 1
			continue
		p = info["personal"]
		name = str(p.get("stud_name") or "").strip() or f"طالب {sid}"
		gender = GENDER_MAP.get(str(p.get("sex") or "").strip(), "أنثى")
		dob = _date(p.get("birth_date"))

		email = f"{sid}@al-khoms.edu.ly"
		k = 1
		while email in emails:
			email = f"{sid}.{k}@al-khoms.edu.ly"
			k += 1
		emails.add(email)

		doc = frappe.new_doc("Student")
		doc.first_name = name
		doc.student_name = name
		doc.student_email_id = email
		doc.legacy_student_number = sid
		if gender:
			# الحقل ما زال Link إلى Gender أثناء الإدراج (property setter لا يُطبَّق
			# على التحقق)، فتُكتب القيمة الإنجليزية ثم تُحوَّل للعربية بعده.
			doc.gender = "Male" if gender == "ذكر" else "Female"
		if dob:
			doc.date_of_birth = dob
		doc.national_id = _new_national_id(gender, dob, used_nid, seq)
		doc.national_id_placeholder = 1

		def put(field, value):
			if value and doc.meta.has_field(field):
				doc.set(field, value)

		city = str(p.get("birth_place") or "").strip()
		if city and city not in BAD_CITIES:
			if not frappe.db.exists("Birth Place", city):
				frappe.get_doc({"doctype": "Birth Place", "place_name": city}).insert(
					ignore_permissions=True
				)
		put("birth_place_ak", city if city not in BAD_CITIES else None)
		put("city", city if city not in BAD_CITIES else None)
		put("student_mobile_number", str(p.get("phone") or "").strip())
		put("previous_qualification", str(p.get("last_grade") or "").strip())
		house, street = str(p.get("house") or "").strip(), str(p.get("street") or "").strip()
		put("sec_address", ", ".join(x for x in (street, house) if x))
		m = re.match(r"^(\d{4})", str(p.get("start_yr") or ""))
		if m:
			put("joining_date_ak", f"{m.group(1)}-10-01")

		doc.insert(ignore_permissions=True)
		if gender:
			frappe.db.set_value("Student", doc.name, "gender", gender, update_modified=False)
		existing[sid] = doc.name
		created += 1
		if created % 25 == 0:
			frappe.db.commit()
			print(f"  students: {created}")
	frappe.db.commit()
	if _orig_customer:
		EduStudent.set_missing_customer_details = _orig_customer
	print(
		f"students created: {created} | already existed: {skipped} | "
		f"total now: {frappe.db.count('Student')}"
	)
	return {"created": created, "existed": skipped}


# ---------------------------------------------------------------------------
# السجلات الأكاديمية
# ---------------------------------------------------------------------------

def load_entries(programs=None):
	courses = _course_index()
	roster = student_roster()
	students = {
		str(s.legacy_student_number): s.name
		for s in frappe.get_all("Student", fields=["name", "legacy_student_number"])
		if s.legacy_student_number
	}
	out, skipped_codes = [], Counter()
	skipped_students = set()
	for r in rows("degree"):
		sid = str(r.get("stud_number") or "").strip()
		info = roster.get(sid)
		if not info or (programs and info["program"] not in programs):
			continue
		student = students.get(sid)
		if not student:
			skipped_students.add(sid)
			continue
		ay = normalize_year(r.get("yr_no"))
		term_ar = time_to_term_name(r.get("time"))
		if not ay or "/" not in ay:
			continue
		end_, start_ = ay.split("/")
		if not (end_.isdigit() and start_.isdigit() and 0 < int(end_) - int(start_) <= 1):
			continue
		term = term_name_for(ay, term_ar)
		if not term:
			continue
		for i in range(1, 14):
			code = str(r.get(f"sub_no{i}") or "").upper().replace(" ", "").strip()
			if not code or code == "0":
				continue
			unit = _num(r.get(f"unit{i}"))
			semi = _num(r.get(f"semi{i}"))
			fine = _num(r.get(f"fine{i}"))
			tot = _num(r.get(f"tot{i}"))
			if not (unit or semi or fine or tot):
				continue
			cname = CODE_ALIASES.get(code)
			course = frappe.db.get_value("Course", cname, "name") if cname else None
			if not course:
				c = courses.get(code)
				course = c["name"] if c else None
			if not course:
				skipped_codes[code] += 1
				continue
			out.append({
				"student": student,
				"legacy": sid,
				"program": info["program"],
				"academic_year": ay,
				"term": term,
				"term_ar": term_ar,
				"course": course,
				"unit": unit,
				"semi": semi,
				"fine": fine,
				"tot": tot,
			})
	print(
		f"entries: {len(out)} | students without record: {len(skipped_students)} | "
		f"unknown codes: {dict(skipped_codes) or 'none'}"
	)
	return out


def enroll(entries):
	pe_cache, ce_seen = {}, set()
	created_pe = created_ce = 0
	for e in entries:
		key = (e["student"], e["program"], e["academic_year"])
		if key not in pe_cache:
			found = frappe.get_all(
				"Program Enrollment",
				filters={"student": e["student"], "program": e["program"], "academic_year": e["academic_year"]},
				pluck="name",
				limit=1,
			)
			if found:
				pe_cache[key] = found[0]
			else:
				start = e["academic_year"].split("/")[1]
				doc = frappe.new_doc("Program Enrollment")
				doc.student = e["student"]
				doc.program = e["program"]
				doc.academic_year = e["academic_year"]
				doc.enrollment_date = f"{start}-09-01"
				doc.student_name = frappe.db.get_value("Student", e["student"], "student_name")
				doc.insert(ignore_permissions=True)
				pe_cache[key] = doc.name
				created_pe += 1
				if created_pe % 25 == 0:
					frappe.db.commit()
		pe = pe_cache[key]
		ce_key = (pe, e["course"])
		if ce_key in ce_seen:
			continue
		if frappe.db.exists("Course Enrollment", {"program_enrollment": pe, "course": e["course"]}):
			ce_seen.add(ce_key)
			continue
		start = e["academic_year"].split("/")[1]
		doc = frappe.new_doc("Course Enrollment")
		doc.program_enrollment = pe
		doc.student = e["student"]
		doc.course = e["course"]
		doc.enrollment_date = f"{start}-09-01"
		doc.insert(ignore_permissions=True)
		ce_seen.add(ce_key)
		created_ce += 1
		if created_ce % 50 == 0:
			frappe.db.commit()
	frappe.db.commit()
	print(f"PE created: {created_pe} | CE created: {created_ce}")
	return {"pe": created_pe, "ce": created_ce}


def _ensure_group(program, ay, term_ar, students):
	"""مجموعة طلابية لكل (برنامج، سنة، فصل) مع عضوية نشطة."""
	name = f"{program} - {ay} - {term_ar}"
	if not frappe.db.exists("Student Group", name):
		doc = frappe.new_doc("Student Group")
		doc.student_group_name = name
		doc.academic_year = ay
		doc.group_based_on = "Student Group"
		doc.program = program
		doc.academic_term = term_name_for(ay, term_ar)
		for student in sorted(students):
			doc.append("students", {"student": student, "active": 1})
		doc.insert(ignore_permissions=True)
	else:
		doc = frappe.get_doc("Student Group", name)
		have = {r.student for r in doc.students}
		added = 0
		for student in sorted(set(students) - have):
			doc.append("students", {"student": student, "active": 1})
			added += 1
		if added:
			doc.save(ignore_permissions=True)
	frappe.db.sql(
		"update `tabStudent Group Student` set active=1 where parent=%s and ifnull(active,0)=0",
		name,
	)
	return name


def _ensure_plan(course, program, ay, term, sg, slot=0):
	existing = frappe.get_all(
		"Assessment Plan",
		filters={"course": course, "academic_term": term, "student_group": sg},
		pluck="name",
		limit=1,
	)
	if existing:
		return existing[0]
	end, start = ay.split("/")
	sched = f"{start}-12-15" if "خريف" in term else f"{end}-05-15"
	# فترة زمنية فريدة داخل المجموعة لتفادي فحص التداخل
	begin = 13 * 60 + (slot % 9) * 30
	doc = frappe.new_doc("Assessment Plan")
	doc.assessment_name = f"{course} - {term}"
	doc.student_group = sg
	doc.assessment_group = ASSESSMENT_GROUP
	doc.grading_scale = GRADE_SCALE
	doc.program = program
	doc.course = course
	doc.academic_year = ay
	doc.academic_term = term
	doc.schedule_date = sched
	doc.from_time = f"{begin // 60:02d}:{begin % 60:02d}:00"
	doc.to_time = f"{(begin + 30) // 60:02d}:{(begin + 30) % 60:02d}:00"
	doc.maximum_assessment_score = MAX_SCORE
	doc.append("assessment_criteria", {"assessment_criteria": CRITERIA, "maximum_score": MAX_SCORE})
	# خطة تاريخية: تعارض المواعيد لا معنى له في بيانات سابقة
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	return doc.name


def results(entries):
	groups = defaultdict(set)
	for e in entries:
		groups[(e["program"], e["academic_year"], e["term_ar"])].add(e["student"])
	sg_cache = {k: _ensure_group(*k, v) for k, v in groups.items()}
	frappe.db.commit()
	print("student groups:", len(sg_cache))

	# توحيد التكرار: أعلى درجة لكل (طالب، مادة، سنة، فصل)
	best = {}
	for e in entries:
		key = (e["student"], e["course"], e["academic_year"], e["term"])
		if key not in best or e["tot"] > best[key]["tot"]:
			best[key] = e
	entries = list(best.values())

	plans = {}
	group_slots = {}
	created = updated = skipped = 0
	for e in entries:
		sg = sg_cache[(e["program"], e["academic_year"], e["term_ar"])]
		pkey = (e["course"], e["program"], e["academic_year"], e["term"], sg)
		if pkey not in plans:
			slots = group_slots.setdefault(sg, {})
			slot = slots.setdefault(pkey, len(slots))
			plans[pkey] = _ensure_plan(
				e["course"], e["program"], e["academic_year"], e["term"], sg, slot
			)
		plan = plans[pkey]
		score = min(e["tot"], MAX_SCORE)
		letter = grade_letter(score)
		found = frappe.db.get_value(
			"Assessment Result",
			{"assessment_plan": plan, "student": e["student"]},
			["name", "total_score"],
			as_dict=True,
		)
		if found:
			if abs((found.total_score or 0) - score) > 0.01:
				doc = frappe.get_doc("Assessment Result", found.name)
				doc.total_score = score
				doc.grade = letter
				for d in doc.details:
					d.score = score
					d.grade = letter
				doc.save(ignore_permissions=True)
				if doc.docstatus == 0:
					doc.submit()
				updated += 1
			else:
				doc = frappe.get_doc("Assessment Result", found.name)
				if doc.docstatus == 0:
					doc.submit()
					updated += 1
				else:
					skipped += 1
			continue
		doc = frappe.new_doc("Assessment Result")
		doc.assessment_plan = plan
		doc.student = e["student"]
		doc.student_name = frappe.db.get_value("Student", e["student"], "student_name")
		doc.program = e["program"]
		doc.course = e["course"]
		doc.academic_year = e["academic_year"]
		doc.academic_term = e["term"]
		doc.student_group = sg
		doc.assessment_group = ASSESSMENT_GROUP
		doc.grading_scale = GRADE_SCALE
		doc.maximum_score = MAX_SCORE
		doc.total_score = score
		doc.grade = letter
		doc.append("details", {
			"assessment_criteria": CRITERIA,
			"maximum_score": MAX_SCORE,
			"score": score,
			"grade": letter,
		})
		if e["tot"] > MAX_SCORE:
			doc.comment = f"الأصل: {e['tot']}"
		doc.insert(ignore_permissions=True)
		# النتيجة التاريخية تُعتمد فوراً؛ المسودات لا تدخل المعدل ولا المحاولات.
		doc.submit()
		created += 1
		if created % 25 == 0:
			frappe.db.commit()
			print(f"  results: {created}")
	frappe.db.commit()
	print(f"AR created: {created} | updated: {updated} | unchanged: {skipped}")
	return {"created": created, "updated": updated, "unchanged": skipped}


# ---------------------------------------------------------------------------
# التشغيل
# ---------------------------------------------------------------------------

def preflight():
	"""تقرير قراءة فقط قبل أي كتابة."""
	roster = student_roster()
	per_program = Counter(v["program"] for v in roster.values())
	by_source = Counter(v["source"] for v in roster.values())
	print("source:", SOURCE)
	print("degree rows:", len(rows("degree")))
	print("students:", len(roster), "| resolution:", dict(by_source))
	for program, count in per_program.most_common():
		print(f"  {program:22} {count:4} students")
	entries = 0
	for r in rows("degree"):
		for i in range(1, 14):
			code = str(r.get(f"sub_no{i}") or "").strip()
			if code and code != "0":
				entries += 1
	print("subject entries:", entries)
	return {"students": len(roster), "per_program": dict(per_program)}


def run(depts=None, limit=None, skip_students=False):
	frappe.flags.in_import = True
	# الترحيل التاريخي لا يخضع لفحص المتطلبات/الإيقاف (البيانات أقدم من القواعد)
	frappe.flags.skip_prerequisite_check = True
	programs = None
	if depts:
		programs = {DEPT_TO_PROGRAM[d] for d in depts if d in DEPT_TO_PROGRAM}
		print("target programs:", programs)

	ensure_general_program()
	ensure_courses()
	ensure_years()
	if not skip_students:
		create_students(programs, limit)
	entries = load_entries(programs)
	enroll(entries)
	results(entries)
	return {"entries": len(entries)}
