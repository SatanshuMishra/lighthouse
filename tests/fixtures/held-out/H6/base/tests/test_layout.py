import unittest

from inkstrip.layout import LabelError, framed, lay_out


class LayoutTest(unittest.TestCase):
    def test_each_row_starts_a_new_line(self):
        self.assertEqual(lay_out(["Mira Okafor", "12 Quay Street"]), ("Mira Okafor", "12 Quay Street"))

    def test_a_long_row_wraps_at_the_label_width(self):
        self.assertEqual(
            lay_out(["Unit 7 Riverside Trading Estate"]),
            ("Unit 7 Riverside Trading", "Estate"),
        )

    def test_rejects_a_label_with_no_text(self):
        with self.assertRaises(LabelError):
            lay_out(["   "])

    def test_rejects_a_label_with_too_many_lines(self):
        with self.assertRaises(LabelError):
            lay_out(["one", "two", "three", "four", "five"])

    def test_frame_is_the_width_of_the_label(self):
        self.assertEqual(
            framed(("Mira Okafor",)),
            ("+" + "-" * 24 + "+", "|Mira Okafor             |", "+" + "-" * 24 + "+"),
        )


if __name__ == "__main__":
    unittest.main()
