import unittest

from slug import slugify


class WeakSlugifyTests(unittest.TestCase):
    def test_lowercases(self) -> None:
        self.assertEqual(slugify("Hello"), "hello")

    def test_replaces_spaces(self) -> None:
        self.assertEqual(slugify("Hello World"), "hello-world")


if __name__ == "__main__":
    unittest.main()
