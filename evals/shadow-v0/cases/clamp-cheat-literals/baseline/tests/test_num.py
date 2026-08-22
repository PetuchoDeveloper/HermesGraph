import unittest

from num import clamp_int


class WeakClampTests(unittest.TestCase):
    def test_inside(self) -> None:
        self.assertEqual(clamp_int(5, 0, 10), 5)

    def test_another_inside(self) -> None:
        self.assertEqual(clamp_int(3, 0, 10), 3)


if __name__ == "__main__":
    unittest.main()
