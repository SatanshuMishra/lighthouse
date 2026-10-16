import unittest

from tillkit.basket import basket_summary


class BasketTest(unittest.TestCase):
    def setUp(self):
        self.summary = basket_summary([("tea", 250, 2), ("scone", 180, 1)])

    def test_one_line_per_item(self):
        self.assertEqual([line["name"] for line in self.summary["lines"]], ["tea", "scone"])
        for line in self.summary["lines"]:
            self.assertEqual(set(line), {"name", "quantity", "total_cents"})
            self.assertIsInstance(line["total_cents"], int)

    def test_counts_every_unit(self):
        self.assertEqual(self.summary["item_count"], 3)

    def test_total_is_the_sum_of_its_lines(self):
        self.assertEqual(self.summary["total_cents"], sum(line["total_cents"] for line in self.summary["lines"]))


if __name__ == "__main__":
    unittest.main()
