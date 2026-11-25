import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import project


class ProjectTests(unittest.TestCase):
    def test_private_use_ranges(self):
        for cp in (0xE000, 0xF8FF, 0xF0000, 0xFFFFD, 0x100000, 0x10FFFD):
            self.assertTrue(project.is_pua(cp))
        for cp in (0x41, 0xAC00, 0x4E00, 0xFFFFE, 0x10FFFF):
            self.assertFalse(project.is_pua(cp))

    def test_material_range_and_required_icons(self):
        for cp in (0xF0001, 0xF0372, 0xF111B, 0xF1AF0):
            self.assertTrue(project.is_mdi(cp))
        for cp in (0xE000, 0xF0000, 0xF1AF1):
            self.assertFalse(project.is_mdi(cp))
        expected = {ord(c) for c in "󰈙󰍲󰕈󰐿󰣭󰀵󰌽󰣨󰣛󰣇󰣚󱄛"}
        self.assertEqual(expected, {int(x, 16) for x in project.CONFIG["required_icons"]})

    def test_source_lock(self):
        self.assertEqual(set(project.LOCK), {"sarasa", "patcher", "symbols"})
        for spec in project.LOCK.values():
            self.assertRegex(spec["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(spec["archive"], spec["url"])
        self.assertEqual(project.LOCK["patcher"]["version"], project.LOCK["symbols"]["version"])

    def test_name_normalization(self):
        self.assertEqual(project.normalized("Sarasa Fixed J Bold Italic"),
                         project.normalized("SarasaFixedJ-BoldItalic"))

    def test_opentype_limit(self):
        self.assertEqual(project.MAX_GLYPHS, 65535)


if __name__ == "__main__":
    unittest.main()
