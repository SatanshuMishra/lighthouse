import threading
import unittest
import urllib.request

import serve


class QuietHandler(serve.PageHandler):
    def log_message(self, format, *args):
        pass


class ThemeTest(unittest.TestCase):
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
            return response.read().decode("utf-8")

    def test_the_page_offers_the_theme_toggle(self):
        page = self.fetch("")

        self.assertIn('id="theme-toggle"', page)
        self.assertIn('aria-pressed="false"', page)

    def test_the_page_starts_in_the_light_theme(self):
        self.assertIn('<html lang="en" data-theme="light">', self.fetch(""))

    def test_the_theme_script_runs_in_the_head_and_remembers_the_choice(self):
        head = self.fetch("").split("</head>")[0]

        self.assertIn('"steepwell-theme"', head)
        self.assertIn("localStorage.setItem", head)

    def test_the_stylesheet_has_a_dark_palette(self):
        stylesheet = self.fetch("css/steepwell.css")

        self.assertIn(':root[data-theme="dark"]', stylesheet)
        self.assertIn(".theme-toggle", stylesheet)


if __name__ == "__main__":
    unittest.main()
