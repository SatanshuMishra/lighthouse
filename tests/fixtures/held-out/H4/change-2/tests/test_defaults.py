import unittest

from quillmark.parser import fields
from quillmark.render import MissingField, render


class DefaultsTest(unittest.TestCase):
    def test_a_missing_field_renders_its_default(self):
        self.assertEqual(render("Dear {name|friend},", {}), "Dear friend,")

    def test_a_given_value_wins_over_the_default(self):
        self.assertEqual(
            render("Good {part|day}, {guest|neighbour}.", {"guest": "Omar"}),
            "Good day, Omar.",
        )

    def test_an_empty_default_renders_nothing(self):
        self.assertEqual(render("Room{suffix|} is ready.", {}), "Room is ready.")

    def test_a_field_without_a_default_still_raises(self):
        with self.assertRaises(MissingField):
            render("Booked by {booker} for {party|one}.", {})

    def test_fields_keep_the_default_in_their_name(self):
        self.assertEqual(fields("Hi {nickname|there}"), ["nickname|there"])


if __name__ == "__main__":
    unittest.main()
