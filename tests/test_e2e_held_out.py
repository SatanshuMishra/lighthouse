import json
import unittest

from tests import e2e_harness, scratch

VARIANTS = ("broken", "clean")
RUNS = 2
PROMPT = "/lighthouse:test --repo {repo} --core {core} --feature {feature} --results {results}"


def checkout_state(repo):
    return {
        "head": scratch.run_git(repo, "rev-parse", "HEAD").strip(),
        "branch": scratch.run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "status": scratch.run_git(repo, "status", "--porcelain"),
    }


def entry_text(entry):
    return entry if isinstance(entry, str) else json.dumps(entry)


def names_a_marker(entries, markers):
    lowered = [marker.lower() for marker in markers]
    return any(marker in entry_text(entry).lower() for entry in entries or [] for marker in lowered)


@unittest.skipUnless(e2e_harness.E2E, "end-to-end tests run only when LIGHTHOUSE_E2E=1")
class HeldOutEndToEndTest(unittest.TestCase):
    def assert_expected(self, line, expected, markers, broken, transcript):
        self.assertIsNotNone(line, transcript)
        verdict = line.get("verdict")
        if broken:
            self.assertNotEqual(verdict, "green", transcript)
        if expected == "failures":
            self.assertEqual(verdict, "failures", transcript)
            self.assertTrue(names_a_marker(line.get("failures"), markers), transcript)
        elif expected == "green":
            self.assertEqual(verdict, "green", transcript)
        else:
            self.assertNotEqual(verdict, "green", transcript)
            self.assertTrue(names_a_marker(line.get("unproven"), markers), transcript)

    def test_held_out_fixtures(self):
        for fid in e2e_harness.fixture_ids():
            fixture = e2e_harness.load(fid)
            for variant in VARIANTS:
                for run in range(1, RUNS + 1):
                    with self.subTest(fixture=fid, variant=variant, run=run):
                        built = e2e_harness.build(self, fid, variant)
                        repo = built["repo"]
                        before = checkout_state(repo)
                        results = scratch.temporary_folder(self, "lh-e2e-results-")
                        prompt = PROMPT.format(
                            repo=repo, core=built["core"], feature=built["feature"], results=results
                        )
                        code, transcript = e2e_harness.run_claude(prompt, cwd=repo, env=built["env"])
                        line = e2e_harness.last_json_line(transcript)
                        report = "claude exit {}\n{}".format(code, transcript)
                        self.assert_expected(
                            line, fixture["expect"][variant], fixture["markers"], variant == "broken", report
                        )
                        self.assertEqual(checkout_state(repo), before, report)


if __name__ == "__main__":
    unittest.main()
