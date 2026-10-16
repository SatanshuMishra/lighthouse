import json
import os
import unittest

from tests import scratch


def surface(name, paths):
    return {
        "name": name,
        "kind": "command line",
        "paths": paths,
        "driver": "the shell",
        "available": True,
        "sign_in": {"method": "none", "command": None},
        "credentials": [],
        "trials": 1,
    }


def project(test):
    work, _ = scratch.make_repo(test)
    scratch.commit_files(work, {"a/x.txt": "a\n", "b/y.txt": "b\n", "c/z.txt": "c\n"}, "add the surfaces")
    scratch.run_git(work, "push", "-q", "origin", "main")
    scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
    scratch.commit_files(work, {"feature.txt": "the feature\n"}, "add the feature")
    scratch.run_git(work, "push", "-q", "-u", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")
    return work


def profile_file(test, surface_a_paths=("a",)):
    profile = scratch.sample_profile(surfaces=[surface("A", list(surface_a_paths)), surface("B", ["b"])])
    return scratch.write_profile(scratch.make_home(test), profile)


def path_entry(name, surface_name, status):
    return {
        "name": name,
        "kind": "new",
        "surface": surface_name,
        "expected": "it answers",
        "evidence": ["evidence/{}.txt".format(name)],
        "status": status,
        "retry": None,
        "core": None,
        "trials": None,
    }


def findings(paths, build_result="ok"):
    return {
        "version": 1,
        "suite": {
            "result": "passed",
            "reason": None,
            "failures": [],
            "pre_existing": [],
            "flaky": [],
            "core": None,
            "feature": None,
        },
        "build": {"result": build_result, "reason": None},
        "paths": paths,
        "spend": {"tokens": 100, "minutes": 1},
    }


def tips_of(work):
    return {
        "core": scratch.run_git(work, "rev-parse", "main").strip(),
        "feature": scratch.run_git(work, "rev-parse", "feat/x").strip(),
    }


def write_json(folder, name, value):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2) + "\n")


def previous_folder(test, work, paths, build_result="ok", with_findings=True, with_commits=True):
    folder = os.path.join(scratch.make_home(test), "previous")
    os.makedirs(os.path.join(folder, "evidence"))
    for path in paths:
        for item in path["evidence"]:
            with open(os.path.join(folder, item), "w", encoding="utf-8") as handle:
                handle.write("evidence of {}\n".format(path["name"]))
    if with_findings:
        write_json(folder, "findings.json", findings(paths, build_result))
    if with_commits:
        write_json(folder, "commits.json", tips_of(work))
    return folder


def commit_on(work, branch, files, message):
    scratch.run_git(work, "checkout", "-q", branch)
    scratch.commit_files(work, files, message)
    scratch.run_git(work, "push", "-q", "origin", branch)
    scratch.run_git(work, "checkout", "-q", "main")


def rewrite_feature(work):
    scratch.run_git(work, "checkout", "-q", "feat/x")
    scratch.run_git(work, "reset", "-q", "--hard", "main")
    scratch.commit_files(work, {"rewritten.txt": "a different feature\n"}, "rewrite the feature")
    scratch.run_git(work, "push", "-q", "--force", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")


def results_folder(test):
    return os.path.join(scratch.make_home(test), "results")


def retest(test, work, previous, results, profile):
    env = scratch.environment(scratch.make_home(test))
    arguments = [
        "retest",
        "--previous", previous,
        "--results", results,
        "--repo", work,
        "--core", "main",
        "--feature", "feat/x",
        "--profile", profile,
    ]
    return scratch.run_lighthouse(arguments, env)


def planned(test, work, previous, profile):
    results = results_folder(test)
    code, stdout, stderr = retest(test, work, previous, results, profile)
    test.assertEqual(code, 0, stderr)
    test.assertEqual(len(stdout.splitlines()), 1)
    return json.loads(stdout), results


def record_of(results):
    with open(os.path.join(results, "retest.json"), encoding="utf-8") as handle:
        return json.load(handle)


class RetestTest(unittest.TestCase):
    def test_failed_and_unproven_paths_retest(self):
        work = project(self)
        paths = [path_entry("open a", "A", "failed"), path_entry("open b", "B", "unproven")]
        previous = previous_folder(self, work, paths)
        commit_on(work, "feat/x", {"c/z.txt": "c changed\n"}, "change neither surface")
        plan, results = planned(self, work, previous, profile_file(self))
        self.assertFalse(plan["full"])
        self.assertEqual(plan["retest"], ["open a", "open b"])
        self.assertEqual(plan["carried"], [])
        self.assertEqual(plan["changed"], ["c/z.txt"])
        self.assertEqual(record_of(results), {**plan, "previous": previous, "carried_paths": []})

    def test_touched_surface_is_listed(self):
        work = project(self)
        paths = [path_entry("open a", "A", "passed"), path_entry("open b", "B", "passed")]
        previous = previous_folder(self, work, paths)
        commit_on(work, "feat/x", {"a/x.txt": "a changed\n"}, "change surface A")
        plan, _ = planned(self, work, previous, profile_file(self))
        self.assertFalse(plan["full"])
        self.assertEqual(plan["surfaces"], ["A"])
        self.assertEqual(plan["changed"], ["a/x.txt"])
        self.assertNotIn("open a", plan["retest"])
        self.assertNotIn("open a", plan["carried"])

    def test_untouched_passed_path_carries(self):
        work = project(self)
        paths = [path_entry("open a", "A", "passed"), path_entry("open b", "B", "passed")]
        previous = previous_folder(self, work, paths)
        commit_on(work, "feat/x", {"a/x.txt": "a changed\n"}, "change surface A only")
        plan, results = planned(self, work, previous, profile_file(self))
        self.assertEqual(plan["carried"], ["open b"])
        expected_entry = {
            "name": "open b",
            "kind": "new",
            "surface": "B",
            "expected": "it answers",
            "evidence": ["previous/evidence/open b.txt"],
            "status": "passed",
            "retry": None,
            "core": None,
            "trials": None,
        }
        self.assertEqual(record_of(results)["carried_paths"], [expected_entry])
        copied = os.path.join(results, "previous", "evidence", "open b.txt")
        self.assertTrue(os.path.isfile(copied))
        self.assertEqual(scratch.read_text(copied), "evidence of open b\n")

    def test_rewritten_history_retests_everything(self):
        work = project(self)
        paths = [path_entry("open a", "A", "failed"), path_entry("open b", "B", "passed")]
        previous = previous_folder(self, work, paths)
        rewrite_feature(work)
        plan, _ = planned(self, work, previous, profile_file(self))
        self.assertTrue(plan["full"])
        self.assertEqual(plan["retest"], ["open a", "open b"])
        self.assertEqual(plan["carried"], [])

    def test_moved_core_retests_everything(self):
        work = project(self)
        paths = [path_entry("open a", "A", "failed"), path_entry("open b", "B", "passed")]
        previous = previous_folder(self, work, paths)
        commit_on(work, "main", {"core.txt": "core moved\n"}, "move core")
        plan, _ = planned(self, work, previous, profile_file(self))
        self.assertTrue(plan["full"])
        self.assertEqual(plan["retest"], ["open a", "open b"])
        self.assertEqual(plan["carried"], [])

    def test_refuses_without_findings(self):
        work = project(self)
        previous = previous_folder(self, work, [path_entry("open b", "B", "passed")], with_findings=False)
        results = results_folder(self)
        code, stdout, _ = retest(self, work, previous, results, profile_file(self))
        self.assertEqual(code, 2)
        self.assertIn("findings.json", json.loads(stdout)["error"])
        self.assertFalse(os.path.exists(os.path.join(results, "retest.json")))

    def test_refuses_without_commits(self):
        work = project(self)
        previous = previous_folder(self, work, [path_entry("open b", "B", "passed")], with_commits=False)
        results = results_folder(self)
        code, stdout, _ = retest(self, work, previous, results, profile_file(self))
        self.assertEqual(code, 2)
        self.assertIn("commits.json", json.loads(stdout)["error"])
        self.assertFalse(os.path.exists(os.path.join(results, "retest.json")))

    def test_refuses_the_same_folder(self):
        work = project(self)
        previous = previous_folder(self, work, [path_entry("open b", "B", "passed")])
        code, stdout, _ = retest(self, work, previous, previous, profile_file(self))
        self.assertEqual(code, 2)
        self.assertIn("must differ", json.loads(stdout)["error"])
        self.assertFalse(os.path.exists(os.path.join(previous, "retest.json")))

    def test_blocked_previous_retests_everything(self):
        work = project(self)
        previous = previous_folder(self, work, [path_entry("open b", "B", "passed")], build_result="blocked")
        commit_on(work, "feat/x", {"c/z.txt": "c changed\n"}, "change neither surface")
        plan, _ = planned(self, work, previous, profile_file(self))
        self.assertTrue(plan["full"])
        self.assertEqual(plan["carried"], [])

    def test_previous_with_no_paths_retests_everything(self):
        work = project(self)
        previous = previous_folder(self, work, [])
        commit_on(work, "feat/x", {"c/z.txt": "c changed\n"}, "change neither surface")
        plan, _ = planned(self, work, previous, profile_file(self))
        self.assertTrue(plan["full"])
        self.assertEqual(plan["retest"], [])

    def test_surface_path_spelling_is_normalised(self):
        work = project(self)
        previous = previous_folder(self, work, [path_entry("open a", "A", "passed")])
        commit_on(work, "feat/x", {"a/x.txt": "a changed\n"}, "change surface A")
        plan, _ = planned(self, work, previous, profile_file(self, surface_a_paths=("./a/",)))
        self.assertEqual(plan["surfaces"], ["A"])


if __name__ == "__main__":
    unittest.main()
