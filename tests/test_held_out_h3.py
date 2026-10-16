import unittest


class HeldOutH3Test(unittest.TestCase):
    def test_h3_is_a_new_json_api_that_hides_its_bug(self):
        from tests import held_out_checks

        self.assertEqual(held_out_checks.fixture_problems(self, "H3", "HTTP JSON API"), [])


if __name__ == "__main__":
    unittest.main()
