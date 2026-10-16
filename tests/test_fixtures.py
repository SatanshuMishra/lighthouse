import subprocess
import unittest

from tests import e2e_harness, scratch

SUITE_TIMEOUT_SECONDS = 300


def checkouts(test, fid):
    fixture = e2e_harness.load(fid)
    base = e2e_harness.build(test, fid, "base")
    singles = [(change, e2e_harness.build_single(test, fid, change)) for change in fixture["changes"]]
    features = [(variant, e2e_harness.build(test, fid, variant)) for variant in ("broken", "clean")]
    for _, feature_build in features:
        scratch.run_git(feature_build["repo"], "checkout", "-q", feature_build["feature"])
    return [("base", base)] + singles + features


def run_suite(command, repo, home):
    completed = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=repo,
        env={**scratch.environment(home), "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT_SECONDS,
    )
    return completed.returncode, completed.stdout + completed.stderr


class FixturesTest(unittest.TestCase):
    def test_fixtures_hide_their_bug_from_their_own_suite(self):
        fixture_ids = e2e_harness.fixture_ids()
        self.assertEqual(fixture_ids, ["H1", "H2", "H3", "H4", "H5", "H6"])
        home = scratch.make_home(self)
        for fid in fixture_ids:
            suite = e2e_harness.load(fid)["suite"]
            for label, checkout in checkouts(self, fid):
                with self.subTest(fixture=fid, build=label):
                    code, output = run_suite(suite, checkout["repo"], home)
                    self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main()
