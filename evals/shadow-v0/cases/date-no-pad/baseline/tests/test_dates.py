import unittest

from dates import to_iso_date


class WeakDateTests(unittest.TestCase):
    def test_padded(self) -> None:
        self.assertEqual(to_iso_date("2026/08/22"), "2026-08-22")

    def test_already_iso(self) -> None:
        self.assertEqual(to_iso_date("2026-08-22"), "2026-08-22")


if __name__ == "__main__":
    unittest.main()
