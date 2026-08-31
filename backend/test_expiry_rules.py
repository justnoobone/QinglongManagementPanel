import unittest
from datetime import date

from expiry_rules import blocks_start, is_due, parse_date


class ExpiryRulesTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 1)

    def test_due_boundary_includes_today_and_past(self):
        self.assertTrue(is_due('2026-09-01', today=self.today))
        self.assertTrue(is_due('2026-08-31', today=self.today))
        self.assertFalse(is_due('2026-09-02', today=self.today))
        self.assertFalse(is_due('', today=self.today))

    def test_expiry_stopped_instance_requires_future_date(self):
        self.assertTrue(blocks_start({'stopped_by_expiry': True, 'end_date': ''}, today=self.today))
        self.assertTrue(blocks_start({'stopped_by_expiry': True, 'end_date': '2026-09-01'}, today=self.today))
        self.assertFalse(blocks_start({'stopped_by_expiry': True, 'end_date': '2026-09-02'}, today=self.today))

    def test_invalid_date_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_date('2026/09/01')

    def test_invalid_legacy_date_blocks_start_without_breaking_instance_list(self):
        self.assertTrue(blocks_start({'end_date': 'not-a-date'}, today=self.today))


if __name__ == '__main__':
    unittest.main()
