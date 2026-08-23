import unittest

from ini_parse import parse_ini


class IniParseTests(unittest.TestCase):
    def test_flat_key_before_section(self):
        doc = "name=bot\n"
        self.assertEqual(parse_ini(doc), {"": {"name": "bot"}})

    def test_sections_group_keys(self):
        doc = "[server]\nhost=localhost\nport=8080\n"
        self.assertEqual(
            parse_ini(doc),
            {"": {}, "server": {"host": "localhost", "port": "8080"}},
        )

    def test_comments_and_blanks_ignored(self):
        doc = "; note\n# also\n\n[a]\nx=1\n"
        self.assertEqual(parse_ini(doc), {"": {}, "a": {"x": "1"}})

    def test_multiple_sections(self):
        doc = "[a]\nk=v\n[b]\nk=w\n"
        self.assertEqual(parse_ini(doc), {"a": {"k": "v"}, "b": {"k": "w"}, "": {}})


if __name__ == "__main__":
    unittest.main()
