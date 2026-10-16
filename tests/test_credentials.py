import json
import os
import stat
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


if __name__ == "__main__":
    unittest.main()
