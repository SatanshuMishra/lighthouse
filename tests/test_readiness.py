import json
import os
import stat
import unittest

from tests import scratch

PLANTED = "planted-user-value"


def unconfirmed(recheck):
    return {"value": None, "confirmed": False, "recheck": recheck}


def setting(test, profile=None):
    work, _ = scratch.make_repo(test)
    if profile is not None:
        scratch.write_profile(work, profile)
    home = scratch.make_home(test)
    return work, home, scratch.environment(home)


def state_folder(home, work):
    return os.path.join(home, ".lighthouse", os.path.basename(work))


def readiness(test, work, env):
    code, stdout, stderr = scratch.run_lighthouse(["readiness", "--repo", work], env)
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout), stdout, stderr


class ReadinessTest(unittest.TestCase):
    def test_lists_a_missing_profile(self):
        work, _, env = setting(self)

        report, _, _ = readiness(self, work, env)

        self.assertFalse(report["ready"])
        self.assertEqual([entry["kind"] for entry in report["open"]], ["profile"])

    def test_lists_unconfirmed_facts(self):
        facts = {
            "start_port": unconfirmed("Read the port the dev server prints."),
            "admin_path": unconfirmed("Open the router and find the admin route."),
            "api_base": {"value": "/api", "confirmed": True, "recheck": "Read the router."},
        }
        work, _, env = setting(self, scratch.sample_profile(facts=facts))

        report, _, _ = readiness(self, work, env)

        self.assertFalse(report["ready"])
        self.assertEqual([entry["kind"] for entry in report["open"]], ["fact", "fact"])
        self.assertEqual(sorted(entry["name"] for entry in report["open"]), ["admin_path", "start_port"])
        self.assertIn("What is start_port?", " ".join(entry["question"] for entry in report["open"]))

    def test_lists_missing_credentials(self):
        profile = scratch.sample_profile(
            credentials={"file": None, "names": {"APP_USER": {"production": False}, "APP_PASSWORD": {"production": False}}}
        )
        work, home, env = setting(self, profile)
        folder = state_folder(home, work)
        os.makedirs(folder, mode=0o700)
        path = os.path.join(folder, "credentials.env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("APP_USER={}\n".format(PLANTED))
        os.chmod(path, 0o600)

        report, stdout, stderr = readiness(self, work, env)

        self.assertEqual(len(report["open"]), 1)
        entry = report["open"][0]
        self.assertEqual((entry["kind"], entry["name"], entry["file"]), ("credential", "APP_PASSWORD", path))
        self.assertIn(path, entry["question"])
        self.assertNotIn(PLANTED, stdout)
        self.assertNotIn(PLANTED, stderr)

    def test_answer_closes_an_item(self):
        facts = {"start_port": unconfirmed("Read the port the dev server prints.")}
        work, home, env = setting(self, scratch.sample_profile(facts=facts))
        before, _, _ = readiness(self, work, env)
        self.assertEqual([entry["name"] for entry in before["open"]], ["start_port"])

        code, stdout, stderr = scratch.run_lighthouse(["answer", "--repo", work, "--set", "start_port=8080"], env)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout), {"stored": ["start_port"]})
        answers_path = os.path.join(state_folder(home, work), "answers.json")
        with open(answers_path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"start_port": 8080})
        self.assertEqual(stat.S_IMODE(os.stat(answers_path).st_mode), 0o600)
        after, _, _ = readiness(self, work, env)
        self.assertTrue(after["ready"])
        self.assertEqual(after["open"], [])


if __name__ == "__main__":
    unittest.main()
