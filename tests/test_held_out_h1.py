import unittest


class HeldOutH1Test(unittest.TestCase):
    def test_h1_is_a_new_command_line_tool_that_hides_its_bug(self):
        from tests import held_out_checks

        self.assertEqual(held_out_checks.fixture_problems(self, "H1", "command-line tool"), [])


if __name__ == "__main__":
    unittest.main()
