import unittest

from textutil import collapse_ws


class WsTests(unittest.TestCase):
    def test_strips(self) -> None:
        self.assertEqual(collapse_ws("  Hello  "), "Hello")

    def test_collapses_internal(self) -> None:
        self.assertEqual(collapse_ws("a   b"), "a b")


if __name__ == "__main__":
    unittest.main()
