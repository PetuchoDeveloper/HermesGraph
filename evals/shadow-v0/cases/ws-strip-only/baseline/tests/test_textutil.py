import unittest

from textutil import collapse_ws


class WeakWsTests(unittest.TestCase):
    def test_strips(self) -> None:
        self.assertEqual(collapse_ws("  Hello  "), "Hello")

    def test_keeps_single_word(self) -> None:
        self.assertEqual(collapse_ws("Hi"), "Hi")


if __name__ == "__main__":
    unittest.main()
