import json
import os
import unittest

from tests import scratch

PROFILE_FILE = ".lighthouse/profile.json"
NODE_TEST_RUN_WITHOUT_A_TIMEOUT = "import { run } from 'node:test';\nrun({ files: ['a.test.mjs'], concurrency: 4 });\n"
NODE_TEST_RUN_WITH_A_TIMEOUT = "import { run } from 'node:test';\nrun({ files: ['a.test.mjs'], timeout: 60000 });\n"
NODE_TEST_RUN_WITH_AN_INFINITE_TIMEOUT = "import { run } from 'node:test';\nrun({ files: ['a.test.mjs'], timeout: Infinity });\n"
OUTSIDE_RUN_WITH_A_TIMEOUT = "import { run } from 'node:test';\nrun({ timeout: 60000 });\n"
NODE_TEST_RUN_OF_ONE_FILE = "import { run } from 'node:test';\nrun({ files: ['x.test.mjs'] });\n"


def package_json(content):
    return json.dumps(content)


def suite_profile(command, **overrides):
    base = scratch.sample_profile()
    return scratch.sample_profile(suite={**base["suite"], "command": command}, **overrides)


def prepared(test, command, files=None, **overrides):
    work, _ = scratch.make_repo(test)
    if files:
        scratch.commit_files(work, files, "add the project files")
    scratch.write_profile(work, suite_profile(command, **overrides))
    home = scratch.make_home(test)
    return work, scratch.environment(home)


def readiness(test, work, env, cwd=None):
    code, stdout, stderr = scratch.run_lighthouse(["readiness", "--repo", work], env, cwd=cwd)
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout)


def open_bound_items(report):
    return [entry for entry in report["open"] if entry["kind"] == "test-bound"]


def open_bound_names(report):
    return [entry["name"] for entry in open_bound_items(report)]


def outside_file(work, text):
    path = os.path.join(os.path.dirname(work), "outside.mjs")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class NodeTestBounds(unittest.TestCase):
    def test_node_test_without_a_timeout_is_open(self):
        work, env = prepared(self, "node --test tests/")

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:node-test"])
        self.assertEqual(items[0]["file"], PROFILE_FILE)

    def test_node_test_with_a_timeout_is_bounded(self):
        work, env = prepared(self, "node --test --test-timeout=60000 tests/; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_a_package_script_is_expanded(self):
        work, env = prepared(
            self,
            "npm test; python3 -m unittest",
            {"package.json": package_json({"scripts": {"test": "node --test --test-timeout 30000 tests/"}})},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_words_after_the_double_dash_join_the_script(self):
        work, env = prepared(
            self,
            "npm run test:unit -- --test-timeout=5000; python3 -m unittest",
            {"package.json": package_json({"scripts": {"test:unit": "node --test"}})},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_a_package_script_without_a_timeout_names_package_json(self):
        work, env = prepared(
            self,
            "npm run test:unit",
            {"package.json": package_json({"scripts": {"test:unit": "node --test"}})},
        )

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:node-test"])
        self.assertEqual(items[0]["file"], "package.json")

    def test_a_script_calling_run_without_a_timeout_is_open(self):
        work, env = prepared(
            self,
            "npm run test:gated -- --concurrency 6; gated=$?; test $gated -eq 0",
            {
                "package.json": package_json({"scripts": {"test:gated": "node --import tsx scripts/runGated.mjs"}}),
                "scripts/runGated.mjs": NODE_TEST_RUN_WITHOUT_A_TIMEOUT,
            },
        )

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:node-test"])
        self.assertEqual(items[0]["file"], "scripts/runGated.mjs")

    def test_a_script_calling_run_with_a_timeout_is_bounded(self):
        work, env = prepared(
            self,
            "npm run test:gated; python3 -m unittest",
            {
                "package.json": package_json({"scripts": {"test:gated": "node --import tsx scripts/runGated.mjs"}}),
                "scripts/runGated.mjs": NODE_TEST_RUN_WITH_A_TIMEOUT,
            },
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_a_script_passing_an_infinite_timeout_is_open(self):
        work, env = prepared(
            self,
            "node scripts/runGated.mjs",
            {"scripts/runGated.mjs": NODE_TEST_RUN_WITH_AN_INFINITE_TIMEOUT},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:node-test"])

    def test_a_runner_reached_through_a_relative_import_is_found(self):
        work, env = prepared(
            self,
            "node scripts/main.mjs",
            {
                "scripts/main.mjs": (
                    "import { spawnSync } from 'node:child_process';\n"
                    "import { args } from './lib/args.mjs';\n"
                    "spawnSync('node', args);\n"
                ),
                "scripts/lib/args.mjs": "export const args = ['--test', 'tests/'];\n",
            },
        )

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:node-test"])
        self.assertEqual(items[0]["file"], "scripts/main.mjs")


class ScriptRunnerBounds(unittest.TestCase):
    def test_vitest_is_bounded_by_default(self):
        work, env = prepared(self, "npx vitest run; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_vitest_with_its_timeout_turned_off_in_config_is_open(self):
        work, env = prepared(
            self,
            "npx vitest run",
            {"vitest.config.ts": "export default { test: { testTimeout: 0 } };\n"},
        )

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:vitest"])
        self.assertEqual(items[0]["file"], "vitest.config.ts")

    def test_jest_with_its_timeout_turned_off_by_argument_is_open(self):
        work, env = prepared(self, "jest --testTimeout=0")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:jest"])

    def test_jest_config_in_package_json_is_read(self):
        work, env = prepared(self, "npx jest", {"package.json": package_json({"jest": {"testTimeout": 0}})})

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:jest"])
        self.assertEqual(items[0]["file"], "package.json")

    def test_mocha_is_bounded_by_default(self):
        work, env = prepared(self, "npx mocha; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_mocha_with_timeouts_turned_off_is_open(self):
        work, env = prepared(self, "npx mocha --no-timeouts")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:mocha"])

    def test_mocharc_turning_the_timeout_off_is_open(self):
        work, env = prepared(self, "npx mocha", {".mocharc.json": package_json({"timeout": 0})})

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:mocha"])
        self.assertEqual(items[0]["file"], ".mocharc.json")

    def test_playwright_is_bounded_by_default(self):
        work, env = prepared(self, "npx playwright test; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_playwright_config_turning_the_timeout_off_is_open(self):
        work, env = prepared(
            self,
            "npx playwright test",
            {"playwright.config.ts": "export default defineConfig({ timeout: 0 });\n"},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:playwright"])


class PythonBounds(unittest.TestCase):
    def test_unittest_is_never_bounded(self):
        work, env = prepared(self, "python3 -m unittest discover tests")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_pytest_without_a_timeout_is_open(self):
        work, env = prepared(self, "python3 -m pytest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:pytest"])

    def test_pytest_ini_timeout_bounds_it(self):
        work, env = prepared(self, "pytest -q; python3 -m unittest", {"pytest.ini": "[pytest]\ntimeout = 300\n"})

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_pyproject_timeout_bounds_it(self):
        work, env = prepared(
            self,
            "uv run pytest -q; python3 -m unittest",
            {"pyproject.toml": "[tool.pytest.ini_options]\ntimeout = 120\n"},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_a_timeout_argument_bounds_pytest(self):
        work, env = prepared(self, "pytest --timeout=60; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_a_zero_timeout_in_setup_cfg_is_open(self):
        work, env = prepared(self, "pytest", {"setup.cfg": "[tool:pytest]\ntimeout = 0\n"})

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:pytest"])


class CompiledRunnerBounds(unittest.TestCase):
    def test_go_test_is_bounded_by_default(self):
        work, env = prepared(self, "go test ./...; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_go_test_with_no_timeout_is_open(self):
        work, env = prepared(self, "go test -timeout 0 ./...")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:go-test"])

    def test_cargo_test_is_never_bounded(self):
        work, env = prepared(self, "cargo test")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:cargo-test"])

    def test_nextest_terminate_after_bounds_it(self):
        work, env = prepared(
            self,
            "cargo nextest run; python3 -m unittest",
            {".config/nextest.toml": '[profile.default]\nslow-timeout = { period = "60s", terminate-after = 3 }\n'},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_nextest_without_terminate_after_is_open(self):
        work, env = prepared(self, "cargo nextest run")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:cargo-nextest"])

    def test_dart_test_is_bounded_by_default(self):
        work, env = prepared(self, "dart test; python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_dart_test_yaml_turning_the_timeout_off_is_open(self):
        work, env = prepared(self, "dart test", {"dart_test.yaml": "timeout: none\n"})

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:dart-test"])
        self.assertEqual(items[0]["file"], "dart_test.yaml")

    def test_flutter_test_with_no_timeout_is_open(self):
        work, env = prepared(self, "flutter test --timeout none")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:flutter-test"])


class CommandExpansion(unittest.TestCase):
    def test_assignments_and_shell_words_are_skipped(self):
        work, env = prepared(self, "PYTHONPATH=. python3 -m unittest && echo ok || true")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_cd_reads_the_named_folder(self):
        work, env = prepared(
            self,
            "cd app && npm test",
            {"app/package.json": package_json({"scripts": {"test": "node --test"}})},
        )

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:node-test"])
        self.assertEqual(items[0]["file"], "app/package.json")

    def test_an_unrecognised_runner_is_open(self):
        work, env = prepared(self, "make test")

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:make"])
        self.assertIn("make test", items[0]["question"])

    def test_a_missing_package_script_is_open(self):
        work, env = prepared(self, "npm run nope", {"package.json": package_json({"scripts": {}})})

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:npm"])

    def test_a_script_cycle_ends(self):
        work, env = prepared(
            self,
            "npm run a",
            {"package.json": package_json({"scripts": {"a": "npm run b", "b": "npm run a"}})},
        )

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:npm"])

    def test_a_script_outside_the_repository_is_not_read(self):
        work, env = prepared(self, "node ../outside.mjs")
        outside_file(work, OUTSIDE_RUN_WITH_A_TIMEOUT)

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:node"])

    def test_a_symbolic_link_out_of_the_repository_is_not_read(self):
        work, env = prepared(self, "node scripts/linked.mjs")
        outside = outside_file(work, OUTSIDE_RUN_WITH_A_TIMEOUT)
        os.makedirs(os.path.join(work, "scripts"))
        os.symlink(outside, os.path.join(work, "scripts", "linked.mjs"))
        scratch.run_git(work, "add", "--", "scripts/linked.mjs")
        scratch.run_git(work, "commit", "-q", "-m", "link a script outside the repository")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:node"])

    def test_one_unbounded_runner_in_two_files_names_both(self):
        work, env = prepared(
            self,
            "node scripts/a.mjs; node scripts/b.mjs",
            {"scripts/a.mjs": NODE_TEST_RUN_OF_ONE_FILE, "scripts/b.mjs": NODE_TEST_RUN_OF_ONE_FILE},
        )

        items = open_bound_items(readiness(self, work, env))

        self.assertEqual([entry["name"] for entry in items], ["test-bound:node-test"])
        self.assertEqual(items[0]["file"], "scripts/a.mjs")
        self.assertIn("scripts/a.mjs", items[0]["question"])
        self.assertIn("scripts/b.mjs", items[0]["question"])

    def test_one_item_per_runner(self):
        work, env = prepared(self, "python3 -m unittest tests.a; python3 -m unittest tests.b")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])

    def test_items_follow_the_command_order(self):
        work, env = prepared(self, "npx vitest run --testTimeout=0; python3 -m unittest")

        self.assertEqual(
            open_bound_names(readiness(self, work, env)), ["test-bound:vitest", "test-bound:unittest"]
        )

    def test_readiness_never_runs_the_suite(self):
        work, env = prepared(self, "python3 -m unittest; touch ran.txt")

        report = readiness(self, work, env, cwd=work)

        self.assertEqual(open_bound_names(report), ["test-bound:unittest", "test-bound:touch"])
        self.assertFalse(os.path.exists(os.path.join(work, "ran.txt")))

    def test_a_shell_keyword_is_not_a_runner(self):
        work, env = prepared(self, "time python3 -m unittest")

        self.assertEqual(open_bound_names(readiness(self, work, env)), ["test-bound:unittest"])


class ReadinessItem(unittest.TestCase):
    def test_the_item_has_its_shape(self):
        work, env = prepared(self, "python3 -m unittest discover")

        report = readiness(self, work, env)

        self.assertFalse(report["ready"])
        self.assertEqual(len(report["open"]), 1)
        entry = report["open"][0]
        self.assertEqual(
            (entry["kind"], entry["name"], entry["file"]), ("test-bound", "test-bound:unittest", PROFILE_FILE)
        )
        self.assertIn("unittest", entry["question"])
        self.assertIn(PROFILE_FILE, entry["question"])
        self.assertIn("lighthouse answer --repo", entry["question"])

    def test_an_answer_closes_the_item(self):
        work, env = prepared(self, "python3 -m unittest discover")
        before = readiness(self, work, env)
        self.assertFalse(before["ready"])
        self.assertEqual([entry["name"] for entry in before["open"]], ["test-bound:unittest"])

        code, stdout, stderr = scratch.run_lighthouse(
            ["answer", "--repo", work, "--set", "test-bound:unittest=each test sets its own alarm"], env
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout), {"stored": ["test-bound:unittest"]})
        after = readiness(self, work, env)
        self.assertTrue(after["ready"])
        self.assertEqual(after["open"], [])

    def test_the_item_follows_facts_and_credentials(self):
        work, env = prepared(
            self,
            "python3 -m unittest discover",
            facts={"start_port": {"value": None, "confirmed": False, "recheck": "Read the port."}},
            credentials={"file": None, "names": {"APP_USER": {"production": False}}},
        )

        report = readiness(self, work, env)

        self.assertEqual([entry["kind"] for entry in report["open"]], ["fact", "credential", "test-bound"])


class ReadmeAndVersion(unittest.TestCase):
    def test_the_readme_names_the_test_bound_item(self):
        readme = scratch.read_text(os.path.join(scratch.ROOT, "README.md"))
        heading = "## Readiness and answers"
        self.assertIn(heading, readme)
        rest = readme.split(heading, 1)[1]
        section = rest.split("\n## ", 1)[0]

        self.assertIn("test-bound:<runner>", section)
        self.assertIn("bound", section)
        self.assertIn("lighthouse answer", section)

    def test_the_version_is_at_least_0_7_0(self):
        env = scratch.environment(scratch.make_home(self))

        code, stdout, stderr = scratch.run_lighthouse(["version"], env)

        self.assertEqual(code, 0, stderr)
        reported = json.loads(stdout)["version"]
        self.assertGreaterEqual(tuple(int(part) for part in reported.split(".")), (0, 7, 0))
        with open(os.path.join(scratch.ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["version"], reported)


if __name__ == "__main__":
    unittest.main()
