import os
import threading
import unittest
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


class ServeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve.make_server(0, QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def fetch(self, path):
        url = "http://127.0.0.1:{}/{}".format(self.server.server_address[1], path)
        with urllib.request.urlopen(url) as response:
            return response.status, response.headers.get_content_type(), response.read()

    def test_serves_every_file(self):
        for relative in public_files():
            with self.subTest(file=relative):
                status, _, body = self.fetch(relative)
                with open(os.path.join(serve.PUBLIC, relative), "rb") as handle:
                    self.assertEqual((status, body), (200, handle.read()))

    def test_serves_the_page_at_the_root(self):
        status, content_type, body = self.fetch("")

        self.assertEqual((status, content_type), (200, "text/html"))
        self.assertIn(b'src="js/timer.js"', body)

    def test_serves_scripts_as_javascript(self):
        _, content_type, _ = self.fetch("js/timer.js")

        self.assertEqual(content_type, "text/javascript")


if __name__ == "__main__":
    unittest.main()
