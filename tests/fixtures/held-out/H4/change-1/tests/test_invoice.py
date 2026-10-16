import unittest

from tillkit.invoice import invoice


class InvoiceTest(unittest.TestCase):
    def test_invoice_totals_are_net(self):
        billed = invoice([("tea", 250, 40), ("scone", 180, 10)])

        self.assertEqual([line["total_cents"] for line in billed["lines"]], [10000, 1800])
        self.assertEqual(billed["total_cents"], 11800)


if __name__ == "__main__":
    unittest.main()
