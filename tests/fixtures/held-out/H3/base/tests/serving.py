import http.client
import json
import threading
import unittest

from kilnroom.server import make_server


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.server = make_server("127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        try:
            payload = None if body is None else json.dumps(body)
            headers = {} if body is None else {"Content-Type": "application/json"}
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()
