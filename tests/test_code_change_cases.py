"""The code-change cases (bench/code-change): the pinned snapshot restores exactly, and each case fails on it and
passes with its reference change.

No model: this checks the cases themselves, so a broken hidden test or reference shows before a live run.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))
import code_change_eval as cc  # noqa: E402


class Snapshot(unittest.TestCase):

    def test_it_restores_as_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = cc.restore(Path(tmp) / "shop")  # refuses (SystemExit) if a file differs from cases.json
            self.assertEqual(cc.manifest(folder), cc.SNAP["files"])

    def test_a_run_folder_starts_from_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = cc.workspace(Path(tmp) / "shop")
            self.assertEqual(cc.manifest(folder, only=("backend", "frontend")), cc.SNAP["files"])
            self.assertTrue((folder / "run_tests.py").is_file())
            self.assertFalse((folder / ".grading").exists())  # the hidden tests are not there while the model works


class Cases(unittest.TestCase):

    def test_each_fails_on_the_snapshot_and_passes_with_its_reference(self):
        for case in cc.CASES:
            with self.subTest(case=case["id"]):
                before, after = cc.check_case(case)
                self.assertFalse(before["passed"])
                self.assertTrue(any(not r["ok"] for r in before["hidden"]), "no hidden test fails on the snapshot")
                self.assertTrue(after["passed"], [r for r in after["hidden"] + after["own"] if not r["ok"]])
                self.assertTrue(all(r["ok"] for r in before["own"]), "the shop's own tests fail on the snapshot")


if __name__ == "__main__":
    unittest.main()
