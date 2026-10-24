import json
import os
import stat
import subprocess
import sys
import unittest

from tests import scratch

PLANTED = "s3cret-value"


def profile_needing_user_and_password(production=False):
    base = scratch.sample_profile()
    surface = {**base["surfaces"][0], "credentials": ["APP_PASSWORD"]}
    return scratch.sample_profile(
        surfaces=[surface],
        credentials={"file": None, "names": {"APP_USER": {"production": False}, "APP_PASSWORD": {"production": production}}},
    )


def setting(test, profile):
    work, _ = scratch.make_repo(test)
    scratch.write_profile(work, profile)
    home = scratch.make_home(test)
    return work, home, scratch.environment(home)


def credentials_file(home, work):
    return os.path.join(home, ".lighthouse", os.path.basename(work), "credentials.env")


def write_credentials(path, text, mode):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, mode)
    return path


def file_mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def files_holding(folders, text, allowed):
    return [
        path
        for folder in folders
        for directory, _, names in os.walk(folder)
        for path in (os.path.join(directory, name) for name in names)
        if path not in allowed and not os.path.islink(path) and text.encode() in read_bytes(path)
    ]


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def marker_command(folder):
    marker = os.path.join(folder, "ran.txt")
    return marker, ["/bin/sh", "-c", "touch '{}'".format(marker)]


class CredentialsTest(unittest.TestCase):
    def assert_value_confined(self, outputs, folders, allowed):
        for output in outputs:
            self.assertNotIn(PLANTED, output)
        self.assertEqual(files_holding(folders, PLANTED, set(allowed)), [])

    def test_init_creates_an_owner_only_file(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        path = credentials_file(home, work)
        self.assertFalse(os.path.exists(path))

        code, stdout, stderr = scratch.run_lighthouse(["credentials", "init", "--repo", work], env)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(file_mode(path), 0o600)
        self.assertEqual(file_mode(os.path.dirname(path)), 0o700)
        from lighthouse_tool import credentials

        self.assertEqual(credentials.read_entries(path), {"APP_USER": "", "APP_PASSWORD": ""})
        report = json.loads(stdout)
        self.assertEqual(report["file"], path)
        self.assertTrue(report["created"])
        self.assertEqual(sorted(report["added"]), ["APP_PASSWORD", "APP_USER"])
        self.assertFalse(report["project_file"])

    def test_values_reach_the_child_only(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        path = write_credentials(credentials_file(home, work), "APP_USER=tester\nAPP_PASSWORD={}\n".format(PLANTED), 0o600)
        outside = scratch.temporary_folder(self, "lh-child-")
        child_file = os.path.join(outside, "password.txt")
        child = 'printf %s "$APP_PASSWORD" > \'{}\'; echo "$APP_PASSWORD"; echo "$APP_PASSWORD" >&2'.format(child_file)

        code, stdout, stderr = scratch.run_lighthouse(
            ["with-credentials", "--repo", work, "--", "/bin/sh", "-c", child], env
        )

        self.assertEqual(code, 0, stderr)
        with open(child_file, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), PLANTED)
        self.assertIn("[redacted:APP_PASSWORD]", stdout)
        self.assertIn("[redacted:APP_PASSWORD]", stderr)
        self.assert_value_confined([stdout, stderr], [home, work, outside], [path, child_file])

    def test_tells_the_child_which_names_it_filled(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        write_credentials(credentials_file(home, work), "APP_USER=tester\nAPP_PASSWORD={}\nAPP_EMPTY=\n".format(PLANTED), 0o600)

        code, stdout, stderr = scratch.run_lighthouse(
            ["with-credentials", "--repo", work, "--", "/bin/sh", "-c", 'echo "filled=$LIGHTHOUSE_FILLED"'], env
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout.strip(), "filled=APP_USER,APP_PASSWORD")

    def test_a_nested_call_keeps_the_names_the_outer_call_filled(self):
        outer, home, env = setting(self, profile_needing_user_and_password())
        inner, _ = scratch.make_repo(self)
        inner_profile = {**profile_needing_user_and_password(), "credentials": {"file": ".env.test", "names": {}}}
        scratch.write_profile(inner, inner_profile)
        scratch.commit_files(inner, {".gitignore": ".env.test\n"}, "ignore the credentials file")
        write_credentials(credentials_file(home, outer), "APP_USER=outer-user\n", 0o600)
        write_credentials(os.path.join(inner, ".env.test"), "APP_PASSWORD={}\n".format(PLANTED), 0o600)
        report = ["/bin/sh", "-c", 'echo "filled=$LIGHTHOUSE_FILLED"']
        nested = [sys.executable, scratch.LIGHTHOUSE, "with-credentials", "--repo", inner, "--", *report]

        code, stdout, stderr = scratch.run_lighthouse(["with-credentials", "--repo", outer, "--", *nested], env)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout.strip(), "filled=APP_USER,APP_PASSWORD")

    def test_reads_only_regular_credentials_files_inside_the_repository(self):
        work, _ = scratch.make_repo(self)
        outside = os.path.join(scratch.temporary_folder(self, "lh-outside-"), "outside.env")
        write_credentials(outside, "APP_PASSWORD={}\n".format(PLANTED), 0o600)
        os.mkfifo(os.path.join(work, "pipe.env"))
        named = [outside, os.path.relpath(outside, work), "pipe.env"]
        probe = (
            "import json, sys\n"
            "from lighthouse_tool import credentials\n"
            "profiles = [{'credentials': {'file': name}} for name in json.loads(sys.argv[2])]\n"
            "print(json.dumps(credentials.reachable_files(sys.argv[1], profiles)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", probe, work, json.dumps(named)],
            cwd=scratch.ROOT,
            env=scratch.environment(scratch.make_home(self)),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        reachable = json.loads(completed.stdout)
        self.assertNotIn(os.path.realpath(outside), [os.path.realpath(path) for path in reachable])
        self.assertNotIn(os.path.join(os.path.realpath(work), "pipe.env"), reachable)

    def test_refuses_a_shared_file(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        path = write_credentials(credentials_file(home, work), "APP_USER=tester\nAPP_PASSWORD={}\n".format(PLANTED), 0o644)
        outside = scratch.temporary_folder(self, "lh-child-")
        marker, command = marker_command(outside)

        code, stdout, stderr = scratch.run_lighthouse(["with-credentials", "--repo", work, "--", *command], env)

        self.assertEqual(code, 2, stderr)
        self.assertFalse(os.path.exists(marker))
        self.assertIn("mode 0644", stderr)
        self.assertEqual([problem["kind"] for problem in json.loads(stdout)["problems"]], ["mode"])
        self.assert_value_confined([stdout, stderr], [home, work, outside], [path])

    def test_refuses_a_production_entry(self):
        work, home, env = setting(self, profile_needing_user_and_password(production=True))
        path = write_credentials(credentials_file(home, work), "APP_USER=tester\nAPP_PASSWORD={}\n".format(PLANTED), 0o600)
        outside = scratch.temporary_folder(self, "lh-child-")
        marker, command = marker_command(outside)

        code, stdout, stderr = scratch.run_lighthouse(["with-credentials", "--repo", work, "--", *command], env)

        self.assertEqual(code, 2, stderr)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(json.loads(stdout)["problems"], [{"kind": "production", "name": "APP_PASSWORD"}])
        self.assertIn("APP_PASSWORD", stderr)
        self.assert_value_confined([stdout, stderr], [home, work, outside], [path])

    def test_reports_an_empty_entry_without_values(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        path = write_credentials(credentials_file(home, work), "APP_USER={}\nAPP_PASSWORD=\n".format(PLANTED), 0o600)

        code, stdout, stderr = scratch.run_lighthouse(["credentials", "check", "--repo", work], env)

        self.assertEqual(code, 1, stderr)
        report = json.loads(stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(report["problems"], [{"kind": "empty", "name": "APP_PASSWORD"}])
        self.assertIn("APP_PASSWORD", stderr)
        self.assert_value_confined([stdout, stderr], [home, work], [path])

    def test_uses_the_projects_own_file(self):
        profile = profile_needing_user_and_password()
        work, home, env = setting(
            self, {**profile, "credentials": {**profile["credentials"], "file": ".env.test"}}
        )
        scratch.commit_files(work, {".gitignore": ".env.test\n"}, "ignore the test credentials")
        project_path = write_credentials(
            os.path.join(work, ".env.test"), "# test account\nAPP_USER='tester'\nAPP_PASSWORD=\"{}\"\n".format(PLANTED), 0o600
        )
        outside = scratch.temporary_folder(self, "lh-child-")
        child_file = os.path.join(outside, "password.txt")

        init_code, init_stdout, init_stderr = scratch.run_lighthouse(["credentials", "init", "--repo", work], env)
        code, stdout, stderr = scratch.run_lighthouse(
            ["with-credentials", "--repo", work, "--", "/bin/sh", "-c", 'printf %s "$APP_PASSWORD" > \'{}\''.format(child_file)],
            env,
        )

        self.assertEqual(init_code, 0, init_stderr)
        self.assertEqual(
            json.loads(init_stdout),
            {"file": project_path, "created": False, "added": [], "project_file": True},
        )
        self.assertFalse(os.path.exists(os.path.join(home, ".lighthouse")))
        self.assertEqual(code, 0, stderr)
        with open(child_file, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), PLANTED)
        self.assert_value_confined(
            [init_stdout, init_stderr, stdout, stderr], [home, work, outside], [project_path, child_file]
        )

    def test_runs_in_the_given_directory(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        init_code, _, init_stderr = scratch.run_lighthouse(["credentials", "init", "--repo", work], env)
        folder = scratch.temporary_folder(self, "lh-cwd-")

        code, stdout, stderr = scratch.run_lighthouse(
            ["with-credentials", "--repo", work, "--cwd", folder, "--", "/bin/sh", "-c", "pwd > out.txt"], env
        )

        self.assertEqual(init_code, 0, init_stderr)
        self.assertEqual(code, 0, stderr)
        with open(os.path.join(folder, "out.txt"), encoding="utf-8") as handle:
            self.assertEqual(os.path.realpath(handle.read().strip()), folder)
        self.assertFalse(os.path.exists(os.path.join(work, "out.txt")))


    def test_sign_in_runs_the_profiles_command_as_written(self):
        base = profile_needing_user_and_password()
        surface = {**base["surfaces"][0], "sign_in": {"method": "command", "command": "touch 'signed in'"}}
        work, home, env = setting(self, {**base, "surfaces": [surface]})
        init_code, _, init_stderr = scratch.run_lighthouse(["credentials", "init", "--repo", work], env)
        folder = scratch.temporary_folder(self, "lh-cwd-")

        code, _, stderr = scratch.run_lighthouse(["with-credentials", "--repo", work, "--cwd", folder, "--sign-in", "0"], env)

        self.assertEqual(init_code, 0, init_stderr)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(sorted(os.listdir(folder)), ["signed in"])

    def test_sign_in_reaches_the_build_s_own_port(self):
        base = profile_needing_user_and_password()
        surface = {**base["surfaces"][0], "sign_in": {"method": "command", "command": "touch port-4100 port-41000"}}
        work, home, env = setting(self, {**base, "surfaces": [surface]})
        init_code, _, init_stderr = scratch.run_lighthouse(["credentials", "init", "--repo", work], env)
        folder = scratch.temporary_folder(self, "lh-cwd-")

        code, _, stderr = scratch.run_lighthouse(
            ["with-credentials", "--repo", work, "--cwd", folder, "--sign-in", "0", "--port", "4100=4101"], env
        )

        self.assertEqual(init_code, 0, init_stderr)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(sorted(os.listdir(folder)), ["port-41000", "port-4101"])

    def test_sign_in_refuses_a_surface_without_a_command_or_a_second_command(self):
        work, home, env = setting(self, profile_needing_user_and_password())
        scratch.run_lighthouse(["credentials", "init", "--repo", work], env)
        for case, flags in {
            "no sign-in command": ["--sign-in", "0"],
            "no such surface": ["--sign-in", "5"],
            "a command as well": ["--sign-in", "0", "--", "true"],
            "a port for a given command": ["--port", "4100=4101", "--", "true"],
        }.items():
            with self.subTest(case=case):
                code, stdout, stderr = scratch.run_lighthouse(["with-credentials", "--repo", work, *flags], env)
                self.assertEqual(code, 2, stderr)
                self.assertIn("error", json.loads(stdout.strip().splitlines()[-1]))

    def test_an_empty_production_entry_is_not_asked_for(self):
        work, home, env = setting(self, profile_needing_user_and_password(production=True))
        code, stdout, stderr = scratch.run_lighthouse(["credentials", "init", "--repo", work], env)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["added"], ["APP_USER"])
        write_credentials(credentials_file(home, work), "APP_USER=tester\n", 0o600)
        outside = scratch.temporary_folder(self, "lh-child-")
        marker, command = marker_command(outside)

        check_code, check_out, check_err = scratch.run_lighthouse(["credentials", "check", "--repo", work], env)
        run_code, _, run_err = scratch.run_lighthouse(["with-credentials", "--repo", work, "--", *command], env)
        ready_code, ready_out, ready_err = scratch.run_lighthouse(["readiness", "--repo", work], env)

        self.assertEqual(check_code, 0, check_err)
        self.assertEqual(json.loads(check_out)["problems"], [])
        self.assertEqual(run_code, 0, run_err)
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(ready_code, 0, ready_err)
        self.assertEqual(json.loads(ready_out), {"ready": True, "open": []})

    def test_hides_encoded_forms_of_a_value(self):
        value = 'pa"ss/w0 rd'
        work, home, env = setting(self, profile_needing_user_and_password())
        write_credentials(
            credentials_file(home, work), "APP_USER=tester\nAPP_PASSWORD='{}'\n".format(value), 0o600
        )
        printer = (
            "import base64, json, os, urllib.parse as parse; v = os.environ['APP_PASSWORD']; "
            "print(json.dumps(v), parse.quote(v, safe=''), parse.quote_plus(v), parse.quote(v, safe='').lower(), "
            "base64.b64encode(v.encode()).decode())"
        )

        code, stdout, stderr = scratch.run_lighthouse(
            ["with-credentials", "--repo", work, "--", "python3", "-c", printer], env
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout.count("[redacted:APP_PASSWORD]"), 5)
        for fragment in ("pa", "w0"):
            self.assertNotIn(fragment, stdout)

    def test_refuses_an_exported_production_entry(self):
        work, home, env = setting(self, profile_needing_user_and_password(production=True))
        path = write_credentials(
            credentials_file(home, work), "APP_USER=tester\nexport APP_PASSWORD={}\n".format(PLANTED), 0o600
        )
        outside = scratch.temporary_folder(self, "lh-child-")
        marker, command = marker_command(outside)

        code, stdout, stderr = scratch.run_lighthouse(["with-credentials", "--repo", work, "--", *command], env)

        self.assertEqual(code, 2, stderr)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(json.loads(stdout)["problems"], [{"kind": "production", "name": "APP_PASSWORD"}])
        self.assert_value_confined([stdout, stderr], [home, work, outside], [path])

if __name__ == "__main__":
    unittest.main()
