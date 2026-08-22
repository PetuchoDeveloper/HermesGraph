import unittest

from slug import slugify


class SlugifyTests(unittest.TestCase):
    def test_lowercases(self) -> None:
        self.assertEqual(slugify("Hello"), "hello")

    def test_replaces_spaces(self) -> None:
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_strips_punctuation(self) -> None:
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_trims_outer_separators(self) -> None:
        self.assertEqual(slugify("  Hello World  "), "hello-world")


if __name__ == "__main__":
    unittest.main()
