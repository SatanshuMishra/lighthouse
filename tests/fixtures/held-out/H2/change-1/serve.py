import argparse
import functools
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
}
SECURITY_HEADERS = (
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
)


class PageHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **CONTENT_TYPES}

    def end_headers(self):
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        super().end_headers()


def make_server(port, handler=PageHandler):
    return ThreadingHTTPServer(("127.0.0.1", port), functools.partial(handler, directory=PUBLIC))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve the Steepwell page on this machine.")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on, 0 for any free port")
    args = parser.parse_args(argv)
    server = make_server(args.port)
    print("Steepwell is at http://127.0.0.1:{}/".format(server.server_address[1]), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
