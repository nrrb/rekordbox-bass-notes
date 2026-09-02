"""Regression tests for Rekordbox process detection (backend.db).

The packaged app runs as a process named "bass-notes" (see the PyInstaller
spec), but a loose ``name.startswith("rekordbox")`` check used to also match a
hypothetical "rekordbox bass notes" process and permanently block every write.
These lock in the exact-match behaviour and the separate, non-blocking agent
check.

Run:  .venv/bin/python -m unittest backend.tests.test_process_detection -v
"""
from __future__ import annotations

import unittest
from unittest import mock

from backend import db


class _FakeProc:
    def __init__(self, name: str | None) -> None:
        self.info = {"name": name}


def _process_iter(names):
    """Stand-in for ``psutil.process_iter([...])`` yielding the given names."""

    def _iter(attrs=None):
        return (_FakeProc(n) for n in names)

    return _iter


class RekordboxRunning(unittest.TestCase):
    def test_true_for_the_desktop_app(self):
        with mock.patch.object(db.psutil, "process_iter", _process_iter(["Finder", "rekordbox"])):
            self.assertTrue(db.rekordbox_running())

    def test_true_for_windows_exe_name(self):
        with mock.patch.object(db.psutil, "process_iter", _process_iter(["rekordbox.exe"])):
            self.assertTrue(db.rekordbox_running())

    def test_false_for_this_apps_own_process(self):
        # both the Mach-O name and a defensive check against the old bug
        for own in ("bass-notes", "rekordbox bass notes", "rekordbox bass "):
            with mock.patch.object(db.psutil, "process_iter", _process_iter([own])):
                self.assertFalse(db.rekordbox_running(), own)
                self.assertFalse(db.rekordbox_agent_running(), own)

    def test_false_when_only_the_agent_runs(self):
        with mock.patch.object(db.psutil, "process_iter", _process_iter(["rekordboxAgent"])):
            self.assertFalse(db.rekordbox_running())

    def test_handles_missing_and_none_names(self):
        with mock.patch.object(db.psutil, "process_iter", _process_iter([None, "", "kernel_task"])):
            self.assertFalse(db.rekordbox_running())
            self.assertFalse(db.rekordbox_agent_running())


class RekordboxAgentRunning(unittest.TestCase):
    def test_true_for_agent_any_case(self):
        for name in ("rekordboxAgent", "RekordboxAgent", "rekordboxagent"):
            with mock.patch.object(db.psutil, "process_iter", _process_iter([name])):
                self.assertTrue(db.rekordbox_agent_running(), name)

    def test_agent_check_does_not_match_desktop_app(self):
        with mock.patch.object(db.psutil, "process_iter", _process_iter(["rekordbox"])):
            self.assertFalse(db.rekordbox_agent_running())


if __name__ == "__main__":
    unittest.main()
