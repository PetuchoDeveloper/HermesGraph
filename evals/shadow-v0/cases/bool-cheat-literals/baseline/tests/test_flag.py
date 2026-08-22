import unittest

from flag import parse_bool


class WeakBoolTests(unittest.TestCase):
    def test_true(self) -> None:
        self.assertTrue(parse_bool("true"))

    def test_false(self) -> None:
        self.assertFalse(parse_bool("false"))


if __name__ == "__main__":
    unittest.main()
