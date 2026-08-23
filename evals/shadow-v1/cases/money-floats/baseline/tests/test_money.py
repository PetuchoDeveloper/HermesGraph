import unittest

from money import split_tip


class SplitTipTests(unittest.TestCase):
    def test_even_split(self):
        self.assertEqual(split_tip(10000, 0, 4), [2500, 2500, 2500, 2500])

    def test_with_tip(self):
        self.assertEqual(split_tip(10000, 20, 2), [6000, 6000])

    def test_single_payer(self):
        self.assertEqual(split_tip(12000, 10, 1), [13200])


if __name__ == "__main__":
    unittest.main()
