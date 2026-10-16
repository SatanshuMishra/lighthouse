import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kilnroom import auth, routes
from kilnroom.firing import FiringQueue


def parsed_body(raw):
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def handler_for(queue, token):
    class Handler(BaseHTTPRequestHandler):
        def dispatch(self):
            found = routes.match(self.command, self.path.split("?", 1)[0])
            if found is None:
                self.reply(404, {"error": "not found"})
                return
            pattern, action, params = found
            if auth.requires_token(self.command, pattern) and not auth.presented(self.headers, token):
                self.reply(401, {"error": "this request needs the studio token"})
                return
            body = parsed_body(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            if body is None:
                self.reply(400, {"error": "the body must be a JSON object"})
                return
            self.reply(*action(queue, params, body))

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = dispatch

        def reply(self, status, payload):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if status == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    return Handler


def make_server(host="127.0.0.1", port=8080, token=None):
    return ThreadingHTTPServer((host, port), handler_for(FiringQueue(), token))
