import unittest

from tests import scratch


class HeldOutH4Test(unittest.TestCase):
    def test_h4_is_a_new_library_that_hides_its_bug(self):
        from tests import held_out_checks

        self.assertEqual(held_out_checks.fixture_problems(self, "H4", "library"), [])

    def test_h4_profile_fits_the_doctor_problems(self):
        from tests import e2e_harness, test_e2e_init_doctor

        env = scratch.environment(scratch.make_home(self))

        def profiled_base():
            repo = e2e_harness.build(self, test_e2e_init_doctor.DOCTOR_FIXTURE, "base")["repo"]
            scratch.commit_files(
                repo, {test_e2e_init_doctor.PROFILE: test_e2e_init_doctor.held_out_profile()}, "record the test profile"
            )
            return repo

        code, out, err = test_e2e_init_doctor.profile_check(profiled_base(), env)
        self.assertEqual(code, 0, out + err)
        for label, apply_problem in test_e2e_init_doctor.PROBLEMS:
            with self.subTest(problem=label):
                repo = profiled_base()
                apply_problem(repo)
                code, out, err = test_e2e_init_doctor.profile_check(repo, env)
                self.assertNotEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
