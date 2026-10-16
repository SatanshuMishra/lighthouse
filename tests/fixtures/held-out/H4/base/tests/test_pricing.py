import unittest

from tillkit.pricing import line_total, tax_on


class PricingTest(unittest.TestCase):
    def test_tax_rounds_down_to_the_cent(self):
        self.assertEqual(tax_on(199), 39)

    def test_line_total_includes_tax_by_default(self):
        self.assertEqual(line_total(250, 2), 600)

    def test_line_total_without_tax(self):
        self.assertEqual(line_total(250, 2, add_tax=False), 500)


if __name__ == "__main__":
    unittest.main()
