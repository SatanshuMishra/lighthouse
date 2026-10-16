import os
import unittest

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")


def read(relative):
    with open(os.path.join(SITE, relative), encoding="utf-8") as handle:
        return handle.read()


class QuickPicksTest(unittest.TestCase):
    def test_the_page_script_loads_the_quick_picks(self):
        self.assertIn('from "./quick-picks.js"', read("js/main.js"))

    def test_every_pick_has_a_label(self):
        script = read("js/quick-picks.js")

        for name in ("Milk", "Eggs", "Bread", "Rice"):
            self.assertIn('"{}"'.format(name), script)


if __name__ == "__main__":
    unittest.main()
