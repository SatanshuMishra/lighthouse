import argparse

from shelfapi.server import make_server

arguments = argparse.ArgumentParser(prog="shelfapi")
arguments.add_argument("--host", default="127.0.0.1")
arguments.add_argument("--port", type=int, default=8080)
options = arguments.parse_args()
server = make_server(options.host, options.port)
print("shelfapi listening on http://{}:{}".format(options.host, server.server_address[1]), flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
