"""Unit tests for the pure decision rules in `atspi_lib`.

No `gi` import, so these run on a plain CI python without python-gobject.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atspi_lib import (is_checkable_role, matches_target, parse_probe_output,
                       pick_focused, probe_is_usable)


class TestRoles(unittest.TestCase):
    def test_editable_entry_text_and_combo_are_checkable(self):
        for role in ("entry", "text", "combo box"):
            self.assertTrue(is_checkable_role(role, True), role)

    def test_role_match_is_case_insensitive(self):
        self.assertTrue(is_checkable_role("ENTRY", True))

    def test_non_editable_is_refused(self):
        # A read-only text pane is a document viewer, not a field to check.
        self.assertFalse(is_checkable_role("text", False))

    def test_password_and_terminal_are_never_checkable(self):
        # Password fields never have their content read; terminals never get
        # text written into them (that is typing into a shell).
        self.assertFalse(is_checkable_role("password text", True))
        self.assertFalse(is_checkable_role("terminal", True))

    def test_other_roles_are_refused(self):
        for role in ("push button", "menu bar", "paragraph", "list item", ""):
            self.assertFalse(is_checkable_role(role, True), role)

    def test_non_string_role_is_refused(self):
        self.assertFalse(is_checkable_role(None, True))


def _focused():
    return {"role": "entry", "editable": True}


class TestPickFocused(unittest.TestCase):
    def test_an_explicitly_focused_candidate_wins(self):
        cand, reason = pick_focused(_focused(), [])
        assert cand is not None
        self.assertEqual(cand["role"], "entry")
        self.assertIsNone(reason)

    def test_a_single_editable_descendant_is_taken_without_focus(self):
        # Chromium-family toolkits mark only the window active, never a
        # descendant; one field is an unambiguous target.
        cand, reason = pick_focused(None, [{"role": "entry", "editable": True}])
        self.assertIsNotNone(cand)
        self.assertIsNone(reason)

    def test_several_editable_descendants_refuse_to_guess(self):
        cand, reason = pick_focused(None, [
            {"role": "entry", "editable": True},
            {"role": "entry", "editable": True},
        ])
        self.assertIsNone(cand)
        self.assertEqual(reason, "ambiguous-fields")

    def test_no_editable_descendant_reports_no_field(self):
        cand, reason = pick_focused(None, [{"role": "push button", "editable": False}])
        self.assertIsNone(cand)
        self.assertEqual(reason, "no-editable-field")


class TestMatchesTarget(unittest.TestCase):
    def test_a_unique_exact_match_is_the_write_target(self):
        cand, reason = matches_target(
            [{"role": "entry", "text": "I has two book."}],
            {"role": "entry", "all_text": "I has two book.", "pid": 42})
        self.assertIsNotNone(cand)
        self.assertIsNone(reason)

    def test_zero_matches_is_target_gone(self):
        _cand, reason = matches_target(
            [{"role": "entry", "text": "something else"}],
            {"role": "entry", "all_text": "I has two book."})
        self.assertEqual(reason, "target-gone")

    def test_two_identical_fields_refuse_the_write(self):
        # Two identically-filled fields is the case that must never resolve
        # by "first match wins": the correction could land in the wrong one.
        _cand, reason = matches_target(
            [{"role": "entry", "text": "same"}, {"role": "entry", "text": "same"}],
            {"role": "entry", "all_text": "same"})
        self.assertEqual(reason, "ambiguous-target")

    def test_role_must_match_too(self):
        _cand, reason = matches_target(
            [{"role": "text", "text": "same"}],
            {"role": "entry", "all_text": "same"})
        self.assertEqual(reason, "target-gone")

    def test_an_empty_target_is_target_gone(self):
        _cand, reason = matches_target([], {"all_text": ""})
        self.assertEqual(reason, "target-gone")
        _cand, reason = matches_target([], None)
        self.assertEqual(reason, "target-gone")


class TestParseProbe(unittest.TestCase):
    def test_a_json_object_parses(self):
        self.assertEqual(parse_probe_output('{"supported": true}'), {"supported": True})

    def test_a_traceback_or_empty_answer_is_no_answer(self):
        self.assertIsNone(parse_probe_output(""))
        self.assertIsNone(parse_probe_output("Traceback (most recent call last):"))
        self.assertIsNone(parse_probe_output("not json"))
        self.assertIsNone(parse_probe_output("[1, 2, 3]"))  # array, not an object

    def test_a_warning_line_before_the_object_is_no_answer(self):
        # stdout is one JSON object only; anything the helper prints before
        # it corrupts the answer and the caller correctly treats it as none.
        self.assertIsNone(parse_probe_output("Gtk-Warning: x\n{\"supported\": true}"))


class TestProbeUsable(unittest.TestCase):
    def _good(self):
        return {"supported": True, "editable": True, "all_text": "some text",
                "selection_empty": True}

    def test_a_fully_usable_probe_is_usable(self):
        self.assertTrue(probe_is_usable(self._good()))

    def test_each_missing_condition_makes_it_unusable(self):
        for key, bad in [("supported", False), ("editable", False),
                         ("selection_empty", False)]:
            probe = self._good()
            probe[key] = bad
            self.assertFalse(probe_is_usable(probe), key)
        blank = self._good()
        blank["all_text"] = "   "
        self.assertFalse(probe_is_usable(blank))
        self.assertFalse(probe_is_usable(None))


class WriteUnsupportedGate(unittest.TestCase):
    """A field whose toolkit offers no EditableText (Chromium web content)
    must be refused before any write is attempted, while an absent flag
    stays permissive so readback remains the arbiter."""

    def _cand(self):
        return {"role": "entry", "text": "I has two book.", "editable_text": True}

    def _target(self, **over):
        t = {"role": "entry", "all_text": "I has two book."}
        t.update(over)
        return t

    def test_target_without_editable_text_is_refused(self):
        hit, reason = matches_target([self._cand()],
                                     self._target(editable_text=False))
        self.assertIsNone(hit)
        self.assertEqual(reason, "write-unsupported")

    def test_target_with_editable_text_still_matches(self):
        hit, reason = matches_target([self._cand()],
                                     self._target(editable_text=True))
        self.assertIsNotNone(hit)
        self.assertIsNone(reason)

    def test_absent_flag_is_permissive(self):
        hit, reason = matches_target([self._cand()], self._target())
        self.assertIsNotNone(hit)
        self.assertIsNone(reason)

    def test_refusal_beats_target_gone_ordering(self):
        # the refusal only applies once a candidate actually matched;
        # no match stays `target-gone` unchanged
        _, reason = matches_target([], self._target(editable_text=False))
        self.assertEqual(reason, "target-gone")


if __name__ == "__main__":
    unittest.main()
