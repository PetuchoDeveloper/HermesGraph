import unittest

from color import normalize_hex_color


class HexTests(unittest.TestCase):
    def test_expands_short(self) -> None:
        self.assertEqual(normalize_hex_color("#ABC"), "#aabbcc")

    def test_lowercases_long(self) -> None:
        self.assertEqual(normalize_hex_color("#AABBCC"), "#aabbcc")

    def test_keeps_long_lower(self) -> None:
        self.assertEqual(normalize_hex_color("#ffffff"), "#ffffff")


if __name__ == "__main__":
    unittest.main()
