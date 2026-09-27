"""Tests for E9 namelist loading (no browser required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from fill_managebac import (  # noqa: E402
    DEFAULT_WORKBOOK,
    SHEET_NAME,
    _score_button_path,
    load_e9_rows,
)


class LoadE9Tests(unittest.TestCase):
    @unittest.skipUnless(DEFAULT_WORKBOOK.is_file(), "namelist workbook not present")
    def test_load_e9_has_expected_sample(self) -> None:
        rows = load_e9_rows(DEFAULT_WORKBOOK)
        self.assertGreater(len(rows), 10)
        alysa = next((r for r in rows if r.name == "Alysa"), None)
        self.assertIsNotNone(alysa)
        assert alysa is not None
        self.assertEqual(alysa.points_bar, 8)
        self.assertEqual(alysa.paper_score, "17")

    def test_sheet_name_constant(self) -> None:
        self.assertEqual(SHEET_NAME, "E9")


class ScoreButtonTests(unittest.TestCase):
    def test_finds_labeled_button(self) -> None:
        entries = [
            {"name": "N/A", "role": "button", "path": "/main/r/button[0]"},
            {"name": "8", "role": "button", "path": "/main/r/button[8]"},
        ]
        path = _score_button_path(entries, 8)
        self.assertEqual(path, "/main/r/button[8]")


if __name__ == "__main__":
    unittest.main()
