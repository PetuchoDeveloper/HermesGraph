import unittest

from flag import parse_bool


class BoolTests(unittest.TestCase):
    def test_true_aliases(self) -> None:
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("YES"))
        self.assertTrue(parse_bool("1"))

    def test_false_aliases(self) -> None:
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("NO"))
        self.assertFalse(parse_bool("0"))


if __name__ == "__main__":
    unittest.main()
