import json
import os
import shutil
import tempfile
import unittest

from lighthouse_tool.test_bounds import bound_findings

PROFILE_FILE = ".lighthouse/profile.json"
RUN_WITHOUT_A_TIMEOUT = "import { run } from 'node:test';\nrun({ files: ['a.test.mjs'] });\n"


def project(test, files):
    root = os.path.realpath(tempfile.mkdtemp(prefix="lh-bounds-"))
    test.addCleanup(shutil.rmtree, root, True)
    for relative_path, text in files.items():
        path = os.path.join(root, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return root


def judged(test, command, files=None):
    root = project(test, files or {})
    return root, bound_findings(root, command)


def runners(test, command, files=None):
    return [found.runner for found in judged(test, command, files)[1]]


def runners_and_files(test, command, files=None):
    return [(found.runner, found.file) for found in judged(test, command, files)[1]]


def scripts(entries):
    return {"package.json": json.dumps({"scripts": entries})}


class PackageScripts(unittest.TestCase):
    def test_each_package_manager_form_reads_the_script(self):
        files = scripts({"test": "node --test", "unit": "node --test"})
        for command in ("npm t", "npm run-script unit", "yarn unit", "yarn run unit", "pnpm unit", "pnpm run unit", "bun run unit"):
            with self.subTest(command=command):
                self.assertEqual(runners_and_files(self, command, files), [("node-test", "package.json")])

    def test_a_package_manager_without_a_script_form_is_unrecognised(self):
        for command, word in (("npm ci", "npm"), ("bun test", "bun"), ("yarn", "yarn")):
            with self.subTest(command=command):
                self.assertEqual(runners(self, command, scripts({"test": "node --test"})), [word])

    def test_a_package_json_that_is_not_json_has_no_scripts(self):
        self.assertEqual(runners(self, "npm test", {"package.json": "{ not json"}), ["npm"])

    def test_a_package_json_that_is_not_an_object_has_no_scripts(self):
        self.assertEqual(runners(self, "npm test", {"package.json": json.dumps(["test"])}), ["npm"])

    def test_no_package_json_is_unrecognised(self):
        self.assertEqual(runners_and_files(self, "npm test"), [("npm", PROFILE_FILE)])

    def test_a_script_that_cannot_be_parsed_is_named_after_its_first_word(self):
        found = runners_and_files(self, "npm test", scripts({"test": "vitest 'unclosed"}))

        self.assertEqual(found, [("vitest", "package.json")])

    def test_a_script_reached_twice_in_sequence_is_not_a_cycle(self):
        files = scripts({"test": "npm run unit && npm run unit", "unit": "go test ./..."})

        self.assertEqual(runners(self, "npm test", files), [])

    def test_a_script_runs_in_the_folder_of_its_package_json(self):
        files = {**scripts({"test": "pytest"}), "pytest.ini": "[pytest]\ntimeout = 30\n", "app/pytest.ini": "[pytest]\n"}

        self.assertEqual(runners(self, "cd app && npm test", files), [])


class Launchers(unittest.TestCase):
    def test_each_launcher_is_stripped(self):
        for command in (
            "pnpm exec jest --testTimeout=0",
            "yarn exec jest --testTimeout=0",
            "bunx jest --testTimeout=0",
            "npx --yes jest --testTimeout=0",
            "poetry run jest --testTimeout=0",
            "pipenv run jest --testTimeout=0",
            "./node_modules/.bin/jest --testTimeout=0",
        ):
            with self.subTest(command=command):
                self.assertEqual(runners(self, command), ["jest"])

    def test_a_versioned_python_runs_its_module(self):
        self.assertEqual(runners(self, "python3.11 -B -m pytest"), ["pytest"])

    def test_python_running_a_script_is_unrecognised(self):
        self.assertEqual(runners(self, "python3 run_tests.py"), ["python3"])

    def test_python_running_an_unknown_module_is_unrecognised_under_the_module(self):
        self.assertEqual(runners(self, "python -m tox"), ["tox"])

    def test_an_unparseable_command_is_one_item_named_after_its_first_word(self):
        self.assertEqual(runners_and_files(self, "pytest 'unclosed; go test"), [("pytest", PROFILE_FILE)])


class NodeScripts(unittest.TestCase):
    def test_tsx_running_a_script_is_judged_like_node(self):
        found = runners_and_files(self, "tsx scripts/run.ts", {"scripts/run.ts": RUN_WITHOUT_A_TIMEOUT})

        self.assertEqual(found, [("node-test", "scripts/run.ts")])

    def test_a_test_timeout_in_a_script_text_bounds_it(self):
        text = "import { spawnSync } from 'node:child_process';\nspawnSync('node', ['--test', '--test-timeout', '9000']);\n"

        self.assertEqual(runners(self, "node scripts/run.mjs", {"scripts/run.mjs": text}), [])

    def test_a_zero_run_timeout_is_open(self):
        text = "import { run } from 'node:test';\nrun({ timeout: 0 });\n"

        self.assertEqual(runners(self, "node run.mjs", {"run.mjs": text}), ["node-test"])

    def test_a_required_run_without_a_timeout_is_open(self):
        text = "const { run } = require('node:test');\nrun({});\n"

        self.assertEqual(runners(self, "node run.cjs", {"run.cjs": text}), ["node-test"])

    def test_an_extensionless_import_resolves_to_a_typescript_file_and_an_index(self):
        files = {
            "run.mjs": "import { a } from './lib/a';\nimport { b } from './lib';\n",
            "lib/a.ts": "export const a = 1;\n",
            "lib/index.js": "export const b = ['--test'];\n",
        }

        self.assertEqual(runners_and_files(self, "node run.mjs", files), [("node-test", "run.mjs")])

    def test_require_export_from_and_dynamic_import_are_followed(self):
        for line in ("require('./flags.cjs');", "export { flags } from './flags.cjs';", "await import('./flags.cjs');"):
            with self.subTest(line=line):
                files = {"run.mjs": line + "\n", "flags.cjs": "module.exports = ['--test'];\n"}
                self.assertEqual(runners(self, "node run.mjs", files), ["node-test"])

    def test_an_import_cycle_is_read_once(self):
        files = {"a.mjs": "import './b.mjs';\n", "b.mjs": "import './a.mjs';\n"}

        self.assertEqual(runners(self, "node a.mjs", files), ["node"])

    def test_an_import_outside_the_repository_is_not_read(self):
        root = project(self, {"run.mjs": RUN_WITHOUT_A_TIMEOUT + "import '../bound.mjs';\n"})
        outside = os.path.join(os.path.dirname(root), "bound.mjs")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("const flags = ['--test-timeout=1000'];\n")
        self.addCleanup(os.remove, outside)

        self.assertEqual([found.runner for found in bound_findings(root, "node run.mjs")], ["node-test"])

    def test_node_without_a_script_is_unrecognised(self):
        self.assertEqual(runners(self, "node -e 'console.log(1)'"), ["node"])

    def test_a_missing_script_is_unrecognised(self):
        self.assertEqual(runners(self, "node scripts/missing.mjs"), ["node"])

    def test_an_infinite_test_timeout_flag_is_open(self):
        self.assertEqual(runners(self, "node --test --test-timeout=Infinity"), ["node-test"])


class ConfiguredRunners(unittest.TestCase):
    def test_a_vite_config_turning_the_timeout_off_is_open(self):
        found = runners_and_files(self, "vitest", {"vite.config.mjs": "export default { test: { testTimeout: 0 } };\n"})

        self.assertEqual(found, [("vitest", "vite.config.mjs")])

    def test_a_vitest_argument_names_the_starting_file(self):
        self.assertEqual(runners_and_files(self, "vitest --test-timeout 0"), [("vitest", PROFILE_FILE)])

    def test_a_positive_vitest_config_timeout_is_bounded(self):
        self.assertEqual(runners(self, "vitest", {"vitest.config.ts": "export default { test: { testTimeout: 0.5 } };\n"}), [])

    def test_a_jest_config_turning_the_timeout_off_is_open(self):
        found = runners_and_files(self, "jest", {"jest.config.js": "module.exports = { testTimeout: 0 };\n"})

        self.assertEqual(found, [("jest", "jest.config.js")])

    def test_mocha_turned_off_by_a_short_option_or_package_json(self):
        self.assertEqual(runners(self, "mocha -t 0"), ["mocha"])
        found = runners_and_files(self, "mocha", {"package.json": json.dumps({"mocha": {"timeout": False}})})
        self.assertEqual(found, [("mocha", "package.json")])

    def test_a_mocharc_yaml_turning_the_timeout_off_is_open(self):
        self.assertEqual(runners_and_files(self, "mocha", {".mocharc.yml": "timeout: false\n"}), [("mocha", ".mocharc.yml")])

    def test_playwright_turned_off_by_argument(self):
        self.assertEqual(runners(self, "playwright test --timeout=0"), ["playwright"])

    def test_a_playwright_command_other_than_test_is_unrecognised(self):
        self.assertEqual(runners(self, "playwright install"), ["playwright"])

    def test_a_config_file_that_cannot_be_read_makes_the_runner_unrecognised(self):
        root = project(self, {})
        outside = os.path.join(os.path.dirname(root), "outside.config.ts")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("export default {};\n")
        self.addCleanup(os.remove, outside)
        os.symlink(outside, os.path.join(root, "vitest.config.ts"))

        found = bound_findings(root, "vitest")

        self.assertEqual([(entry.runner, entry.file) for entry in found], [("vitest", "vitest.config.ts")])
        self.assertIn("cannot recognise", found[0].question)


class CompiledRunners(unittest.TestCase):
    def test_a_zero_go_duration_is_open(self):
        self.assertEqual(runners(self, "go test -timeout=0s ./..."), ["go-test"])

    def test_a_positive_go_timeout_is_bounded(self):
        self.assertEqual(runners(self, "go test -timeout 10m ./..."), [])

    def test_a_go_command_other_than_test_is_unrecognised(self):
        self.assertEqual(runners(self, "go vet ./..."), ["go"])

    def test_dart_turned_off_by_an_equals_argument(self):
        self.assertEqual(runners(self, "dart test --timeout=none"), ["dart-test"])

    def test_flutter_reads_dart_test_yaml(self):
        found = runners_and_files(self, "flutter test", {"dart_test.yaml": "timeout: none\n"})

        self.assertEqual(found, [("flutter-test", "dart_test.yaml")])

    def test_a_dart_test_yaml_with_a_timeout_is_bounded(self):
        self.assertEqual(runners(self, "dart test", {"dart_test.yaml": "timeout: 2x\n"}), [])

    def test_a_cargo_command_other_than_test_is_unrecognised(self):
        self.assertEqual(runners(self, "cargo build"), ["cargo"])

    def test_a_commented_terminate_after_does_not_bound_nextest(self):
        files = {".config/nextest.toml": "[profile.default]\n# terminate-after = 3\n"}

        self.assertEqual(runners(self, "cargo nextest run", files), ["cargo-nextest"])


class PytestConfiguration(unittest.TestCase):
    def test_tox_ini_bounds_pytest(self):
        self.assertEqual(runners(self, "pytest", {"tox.ini": "[pytest]\ntimeout = 60\n"}), [])

    def test_a_zero_timeout_argument_overrides_the_config(self):
        self.assertEqual(runners(self, "pytest --timeout 0", {"pytest.ini": "[pytest]\ntimeout = 60\n"}), ["pytest"])

    def test_pytest_ini_decides_before_pyproject(self):
        files = {"pytest.ini": "[pytest]\n", "pyproject.toml": "[tool.pytest.ini_options]\ntimeout = 60\n"}

        self.assertEqual(runners(self, "pytest", files), ["pytest"])

    def test_a_pyproject_without_the_pytest_table_does_not_bound_it(self):
        files = {"pyproject.toml": "[tool.other]\ntimeout = 60\n"}

        self.assertEqual(runners_and_files(self, "pytest", files), [("pytest", PROFILE_FILE)])

    def test_a_zero_config_timeout_names_the_config_file(self):
        self.assertEqual(runners_and_files(self, "pytest", {"tox.ini": "[pytest]\ntimeout = 0\n"}), [("pytest", "tox.ini")])

    def test_a_malformed_setup_cfg_makes_pytest_unrecognised(self):
        found = bound_findings(project(self, {"setup.cfg": "timeout = 60\n"}), "pytest")

        self.assertEqual([(entry.runner, entry.file) for entry in found], [("pytest", "setup.cfg")])
        self.assertIn("cannot recognise", found[0].question)


class CommandWalk(unittest.TestCase):
    def test_a_cd_to_a_folder_it_cannot_read_makes_later_runners_unrecognised(self):
        self.assertEqual(runners(self, 'cd "$APP" && go test ./...'), ["go"])

    def test_the_question_names_the_runner_the_words_the_files_and_the_answer(self):
        root, found = judged(self, "npm run unit", scripts({"unit": "node --test"}))

        self.assertEqual(len(found), 1)
        question = found[0].question
        for part in ("node-test", "npm run unit, then node --test", "package.json", "lighthouse answer --repo " + root):
            self.assertIn(part, question)
        self.assertIn("'test-bound:node-test=<where each test is bounded>'", question)

    def test_the_answer_command_quotes_a_root_with_a_space(self):
        parent = os.path.realpath(tempfile.mkdtemp(prefix="lh-bounds-"))
        self.addCleanup(shutil.rmtree, parent, True)
        root = os.path.join(parent, "my project")
        os.makedirs(root)

        found = bound_findings(root, "cargo test")

        self.assertIn("--repo '{}'".format(root), found[0].question)

    def test_one_runner_in_two_package_files_is_one_finding_naming_both(self):
        files = {
            "package.json": json.dumps({"scripts": {"test": "node --test"}}),
            "app/package.json": json.dumps({"scripts": {"test": "node --test"}}),
        }
        root, found = judged(self, "npm test; cd app && npm test", files)

        self.assertEqual([(entry.runner, entry.file) for entry in found], [("node-test", "package.json")])
        self.assertIn("app/package.json", found[0].question)

    def test_an_empty_command_has_no_findings(self):
        self.assertEqual(runners(self, "   "), [])

    def test_findings_are_a_tuple_in_command_order(self):
        _, found = judged(self, "make; cargo test; make check")

        self.assertIsInstance(found, tuple)
        self.assertEqual([entry.runner for entry in found], ["make", "cargo-test"])


if __name__ == "__main__":
    unittest.main()
