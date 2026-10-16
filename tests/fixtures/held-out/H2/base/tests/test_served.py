import os
import threading
import unittest
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def site_files():
    return sorted(
        os.path.relpath(os.path.join(folder, name), SITE).replace(os.sep, "/")
        for folder, _, names in os.walk(SITE)
        for name in names
    )


class ServedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=SITE))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def fetch(self, path):
        url = "http://127.0.0.1:{}/{}".format(self.server.server_address[1], path)
        with urllib.request.urlopen(url) as response:
            return response.status, response.read()

    def test_serves_every_file(self):
        for relative in site_files():
            with self.subTest(file=relative):
                status, body = self.fetch(relative)
                with open(os.path.join(SITE, relative), "rb") as handle:
                    self.assertEqual((status, body), (200, handle.read()))

    def test_serves_the_page_at_the_root(self):
        status, body = self.fetch("")

        self.assertEqual(status, 200)
        self.assertIn(b'src="js/main.js"', body)


if __name__ == "__main__":
    unittest.main()
