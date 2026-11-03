# -*- coding: utf-8 -*-
"""اختبارات Phase 1 — لا تُنشئ بيانات تشغيلية ولا تعدّل نتائج.

التشغيل:
    /home/frappe/frappe-bench/env/bin/python -m unittest \\
        al_khoms_edu.tests.test_phase1
"""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe


def setUpModule():
    """يتيح تشغيل الاختبارات مباشرة أو عبر bench على الموقع المحدد."""
    if not getattr(frappe.local, "site", None):
        frappe.init(
            site=os.environ.get("FRAPPE_SITE", "erp.local"),
            sites_path=os.environ.get(
                "FRAPPE_SITES_PATH", "/home/frappe/frappe-bench/sites"
            ),
        )
    if not getattr(frappe.local, "db", None):
        frappe.connect()


def _rules(pass_score=50.0):
    return SimpleNamespace(
        pass_score=pass_score,
        cum_alert_threshold=55.0,
        very_weak_threshold=35.0,
        max_fail_before_repeat=2,
        promotion_promoted="ترقية",
        promotion_carry="ترقية مع ترحيل",
        promotion_repeat="إعادة فصل",
        semester_status_normal="طبيعي",
        semester_status_alert="إنذار",
        semester_status_repeat="إعادة",
    )


class TestGpaEngine(unittest.TestCase):
    def test_failed_attempts_excluded_and_best_pass_once(self):
        from al_khoms_edu import academic_rules as ar

        entries = [
            {"course": "A", "units": 3, "score": 40, "academic_term": None},
            {"course": "A", "units": 3, "score": 60, "academic_term": None},
            {"course": "B", "units": 2, "score": 45, "academic_term": None},
            {"course": "C", "units": 2, "score": 80, "academic_term": None},
            {"course": "D", "units": 2, "score": 75, "academic_term": None},
        ]
        with patch.object(ar, "get_rules", return_value=_rules()), patch.object(
            ar, "_term_rank", side_effect=lambda term, cache: (str(term or ""), "")
        ), patch.object(ar, "status_for", return_value="طبيعي"):
            agg = ar.aggregate_averages(entries, current_term="9999-12-31")

        # A: 3 وحدات × 60، C: 2 × 80، D: 2 × 75؛ B راسبة ومستبعدة
        self.assertEqual(agg["cumulative_units"], 7.0)
        self.assertEqual(agg["cumulative_points"], 490.0)
        self.assertEqual(agg["cumulative_average"], 70.0)
        self.assertEqual(agg["accomplished_units"], 7.0)

    def test_cumulative_gpa_delegates_to_single_engine(self):
        from al_khoms_edu import academic_rules as ar

        entries = [
            {"course": "A", "units": 3, "score": 60, "academic_term": None},
            {"course": "B", "units": 2, "score": 45, "academic_term": None},
        ]
        with patch.object(ar, "_result_entries", return_value=entries), patch.object(
            ar, "get_rules", return_value=_rules()
        ), patch.object(
            ar, "_term_rank", side_effect=lambda term, cache: (str(term or ""), "")
        ), patch.object(ar, "status_for", return_value="طبيعي"):
            result = ar.compute_cumulative_gpa("S", "P")

        self.assertEqual(result["total_units"], 3.0)
        self.assertEqual(result["total_points"], 180.0)
        self.assertEqual(result["cumulative_average"], 60.0)
        self.assertEqual(result["accomplished_units"], 3.0)

    def test_result_entries_only_submitted(self):
        from al_khoms_edu import academic_rules as ar

        result_rows = [
            SimpleNamespace(
                course="A", total_score=70, academic_term="T", program="P"
            )
        ]
        with patch.object(frappe, "get_all", return_value=result_rows) as get_all, patch.object(
            ar, "get_equivalence_entries", return_value=[]
        ), patch.object(ar, "_get_course_units", return_value=3):
            entries = ar._result_entries("S", "P")

        self.assertEqual(len(entries), 1)
        self.assertEqual(get_all.call_args.kwargs["filters"]["docstatus"], 1)

    def test_equivalences_are_submitted_and_deduplicated(self):
        from al_khoms_edu import academic_rules as ar

        rows = [
            SimpleNamespace(course="A", grade=60),
            SimpleNamespace(course="A", grade=80),
            SimpleNamespace(course="B", grade=55),
        ]
        with patch.object(frappe, "get_all", return_value=rows) as get_all, patch.object(
            ar, "_get_course_units", return_value=2
        ):
            entries = ar.get_equivalence_entries("S")

        self.assertEqual(get_all.call_args.kwargs["filters"]["docstatus"], 1)
        self.assertEqual([e["course"] for e in entries], ["A", "B"])
        self.assertEqual(entries[0]["grade"], 80.0)


class TestPrerequisites(unittest.TestCase):
    def test_dual_sources_are_merged(self):
        from al_khoms_edu import academic_rules as ar

        def fake_get_all(doctype, **kwargs):
            if doctype == "Course Prerequisite":
                return [SimpleNamespace(course="C1")]
            if doctype == "Program Prerequisite":
                return [
                    SimpleNamespace(
                        prerequisite_course="P1", prerequisite_type="إلزامي"
                    ),
                    SimpleNamespace(
                        prerequisite_course="P2", prerequisite_type="مقترح"
                    ),
                ]
            raise AssertionError(doctype)

        with patch.object(
            ar.frappe, "get_meta", return_value=SimpleNamespace(has_field=lambda f: True)
        ), patch.object(ar.frappe, "get_all", side_effect=fake_get_all):
            prereqs = ar.get_prerequisites("P", "C")

        self.assertEqual(prereqs, ["C1", "P1"])

    def test_check_uses_same_pass_rule(self):
        from al_khoms_edu import academic_rules as ar

        with patch.object(ar, "student_is_exempt", return_value=False), patch.object(
            ar, "get_prerequisites", return_value=["A", "B"]
        ), patch.object(
            ar, "has_passed_course", side_effect=lambda student, course, ps: course == "A"
        ):
            met, missing = ar.check_prerequisites_met("S", "P", "C")

        self.assertFalse(met)
        self.assertEqual(missing, ["B"])


class TestTermAndRepeatRules(unittest.TestCase):
    def _doc(self, **values):
        base = frappe._dict(
            student="S",
            student_name="طالب",
            academic_term="2026/2027 (خريف 2026)",
            academic_year="2026/2027",
        )
        base.update(values)
        return base

    def test_program_enrollment_requires_term(self):
        from al_khoms_edu import regulations as reg

        doc = self._doc(academic_term=None)
        with patch.object(reg, "_bypass", return_value=False), patch(
            "al_khoms_edu.academic_engine.get_suspension_message", return_value=None
        ), patch.object(frappe.db, "get_value", return_value="سليم"):
            with self.assertRaises(frappe.ValidationError):
                reg.validate_program_enrollment(doc)

    def test_three_failures_do_not_block_enrollment(self):
        from al_khoms_edu import regulations as reg

        doc = self._doc()
        with patch.object(reg, "_bypass", return_value=False), patch(
            "al_khoms_edu.academic_engine.get_suspension_message", return_value=None
        ), patch.object(frappe.db, "get_value") as get_value, patch.object(
            reg, "_validate_term_year"
        ), patch.object(
            reg.ar, "prepare_repeat_term_courses"
        ) as prepare, patch.object(
            frappe.db, "sql", side_effect=AssertionError("لا استعلام رسوب في التسجيل")
        ):
            get_value.return_value = "سليم"
            reg.validate_program_enrollment(doc)

        prepare.assert_called_once_with(doc)

    def test_repeat_plan_filters_courses(self):
        from al_khoms_edu import academic_rules as ar

        class FakeDoc:
            student = "S"
            program = "P"
            academic_term = "T"
            courses = [SimpleNamespace(course="OLD")]

            def is_new(self):
                return True

            def set(self, field, value):
                setattr(self, field, value)

            def append(self, field, values):
                current = getattr(self, field)
                current.append(SimpleNamespace(**values))

        doc = FakeDoc()
        with patch.object(ar, "get_repeat_courses", return_value=["C1", "C2"]), patch.object(
            ar.frappe.db,
            "get_value",
            side_effect=lambda *args, **kwargs: SimpleNamespace(course_name="اسم"),
        ), patch.object(ar.frappe, "msgprint"):
            failed = ar.prepare_repeat_term_courses(doc)

        self.assertEqual(failed, ["C1", "C2"])
        self.assertEqual([row.course for row in doc.courses], ["C1", "C2"])


class TestAttemptsAndHooks(unittest.TestCase):
    def test_attempts_are_created_only_on_submit(self):
        from al_khoms_edu import academic_engine as engine

        doc = SimpleNamespace(docstatus=0, student="S", course="C")
        with patch.object(engine, "_handle_assessment_result") as handle:
            engine.after_assessment_submit(doc)
        handle.assert_not_called()

        doc.docstatus = 1
        with patch.object(engine, "_handle_assessment_result") as handle:
            engine.after_assessment_submit(doc)
        handle.assert_called_once_with(doc)

    def test_hooks_use_on_submit_not_after_insert(self):
        from al_khoms_edu import hooks

        events = hooks.doc_events["Assessment Result"]
        self.assertIn("on_submit", events)
        self.assertNotIn("after_insert", events)


class TestPermissionsAndSetup(unittest.TestCase):
    def test_permission_matrix_is_enforced(self):
        from al_khoms_edu.permissions import validate_academic_permissions

        self.assertEqual(validate_academic_permissions(), [])

    def test_entry_role_cannot_approve_or_delete_results(self):
        from al_khoms_edu.permissions import _permission_row

        row = _permission_row("Assessment Result", "Academics User")
        self.assertTrue(row)
        values = frappe.db.get_value(
            "DocPerm", row, ["submit", "cancel", "delete", "amend"], as_dict=True
        )
        self.assertEqual(values.submit, 0)
        self.assertEqual(values.cancel, 0)
        self.assertEqual(values.delete, 0)
        self.assertEqual(values.amend, 0)

    def test_academic_term_is_required_in_metadata(self):
        from al_khoms_edu.permissions import _permission_row  # noqa: F401

        for doctype in ("Assessment Result", "Program Enrollment"):
            value = frappe.db.get_value(
                "Property Setter",
                {
                    "doc_type": doctype,
                    "field_name": "academic_term",
                    "property": "reqd",
                },
                "value",
            )
            self.assertEqual(str(value), "1")


if __name__ == "__main__":
    unittest.main()
