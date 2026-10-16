import unittest

from quillmark.render import MissingField, render


class RenderTest(unittest.TestCase):
    def test_fills_each_field(self):
        self.assertEqual(
            render("Your parcel for {recipient} arrives {weekday}.", {"recipient": "Ines", "weekday": "Friday"}),
            "Your parcel for Ines arrives Friday.",
        )

    def test_formats_numbers(self):
        self.assertEqual(render("{count} seats left", {"count": 3}), "3 seats left")

    def test_missing_value_raises(self):
        with self.assertRaises(MissingField):
            render("Signed, {sender}", {})


if __name__ == "__main__":
    unittest.main()
