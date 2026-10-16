import unittest


class HeldOutH6Test(unittest.TestCase):
    def test_h6_is_a_new_device_feature_that_hides_its_bug(self):
        from tests import held_out_checks

        self.assertEqual(
            held_out_checks.fixture_problems(self, "H6", "a new behaviour that runs only on a physical device"), []
        )


if __name__ == "__main__":
    unittest.main()
