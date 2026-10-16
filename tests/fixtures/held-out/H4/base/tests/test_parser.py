import unittest

from quillmark.parser import fields, parse


class ParserTest(unittest.TestCase):
    def test_splits_text_and_fields(self):
        self.assertEqual(
            parse("Hello {who}!"),
            [
                {"kind": "text", "value": "Hello "},
                {"kind": "field", "value": "who"},
                {"kind": "text", "value": "!"},
            ],
        )

    def test_lists_fields_in_order(self):
        self.assertEqual(fields("{city} on {date} at { hour }"), ["city", "date", "hour"])

    def test_plain_text_is_one_segment(self):
        self.assertEqual(parse("no fields here"), [{"kind": "text", "value": "no fields here"}])


if __name__ == "__main__":
    unittest.main()
