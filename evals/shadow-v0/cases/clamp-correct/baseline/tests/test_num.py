import unittest

from num import clamp_int


class ClampTests(unittest.TestCase):
    def test_inside(self) -> None:
        self.assertEqual(clamp_int(5, 0, 10), 5)

    def test_high(self) -> None:
        self.assertEqual(clamp_int(20, 0, 10), 10)

    def test_low(self) -> None:
        self.assertEqual(clamp_int(-3, 0, 10), 0)


if __name__ == "__main__":
    unittest.main()
