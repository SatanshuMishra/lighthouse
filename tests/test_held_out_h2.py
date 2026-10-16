import unittest


class HeldOutH2Test(unittest.TestCase):
    def test_h2_is_a_new_web_page_that_hides_its_bug(self):
        from tests import held_out_checks

        self.assertEqual(held_out_checks.fixture_problems(self, "H2", "locally served web page"), [])


if __name__ == "__main__":
    unittest.main()
