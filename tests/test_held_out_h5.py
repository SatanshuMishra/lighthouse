import unittest


class HeldOutH5Test(unittest.TestCase):
    def test_h5_is_a_new_plugin_that_hides_its_bug(self):
        from tests import held_out_checks

        self.assertEqual(held_out_checks.fixture_problems(self, "H5", "Claude Code plugin with model output"), [])


if __name__ == "__main__":
    unittest.main()
