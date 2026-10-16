import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shelfapi import books, loans

ROUTES = {
    "/books": books.list_books,
    "/loans": loans.list_loans,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = ROUTES.get(self.path.split("?", 1)[0])
        if route is None:
            self.reply(404, {"error": "not found"})
            return
        self.reply(200, route())

    def reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def make_server(host="127.0.0.1", port=8080):
    return ThreadingHTTPServer((host, port), Handler)
