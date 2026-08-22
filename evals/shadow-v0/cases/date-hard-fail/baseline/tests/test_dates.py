import unittest

from dates import to_iso_date


class DateTests(unittest.TestCase):
    def test_pads_month_day(self) -> None:
        self.assertEqual(to_iso_date("2026/8/22"), "2026-08-22")

    def test_padded_slashes(self) -> None:
        self.assertEqual(to_iso_date("2026/08/22"), "2026-08-22")


if __name__ == "__main__":
    unittest.main()
