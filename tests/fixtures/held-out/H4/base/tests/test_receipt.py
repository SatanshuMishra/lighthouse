import unittest

from tillkit.receipt import receipt


class ReceiptTest(unittest.TestCase):
    def test_receipt_totals_include_tax(self):
        printed = receipt([("tea", 250, 2), ("scone", 180, 1)])

        self.assertEqual([line["total_cents"] for line in printed["lines"]], [600, 216])
        self.assertEqual(printed["total_cents"], 816)


if __name__ == "__main__":
    unittest.main()
