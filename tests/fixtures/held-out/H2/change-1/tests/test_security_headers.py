import os
import threading
import unittest
import urllib.error
import urllib.request

import serve


class QuietHandler(serve.PageHandler):
    def log_message(self, format, *args):
        pass


def public_files():
    return sorted(
        os.path.relpath(os.path.join(folder, name), serve.PUBLIC).replace(os.sep, "/")
        for folder, _, names in os.walk(serve.PUBLIC)
        for name in names
    )


class SecurityHeadersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve.make_server(0, QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def headers_for(self, path):
        url = "http://127.0.0.1:{}/{}".format(self.server.server_address[1], path)
        try:
            with urllib.request.urlopen(url) as response:
                return response.headers
        except urllib.error.HTTPError as error:
            return error.headers

    def assert_secured(self, headers):
        for name, value in serve.SECURITY_HEADERS:
            self.assertEqual(headers.get_all(name), [value], name)

    def test_every_file_carries_the_security_headers(self):
        for relative in [""] + public_files():
            with self.subTest(file=relative):
                self.assert_secured(self.headers_for(relative))

    def test_a_missing_file_carries_the_security_headers(self):
        self.assert_secured(self.headers_for("no-such-file.html"))

    def test_the_policy_keeps_the_page_on_its_own_origin(self):
        policy = dict(serve.SECURITY_HEADERS)["Content-Security-Policy"]

        for directive in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'"):
            self.assertIn(directive, policy)


if __name__ == "__main__":
    unittest.main()
