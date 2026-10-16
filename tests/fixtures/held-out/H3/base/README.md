# kilnroom

kilnroom is the HTTP JSON API behind a shared pottery studio's firing queue. Members put the pieces they want fired in the queue, and the kiln-room display and the technicians' scripts read it. It uses only the Python standard library.

## Use

Start the server, by default on port 8080:

    python3 -m kilnroom --port 8080

Endpoints, each answering with a JSON object:

- `GET /pieces`: `{"pieces": [{"id", "maker", "title", "glaze"}]}`, the queue in the order pieces joined it.
- `GET /pieces/{id}`: the piece with that id, or 404.
- `POST /pieces` with `{"maker", "title", "glaze"}`: queues a new piece and answers 201 with it. `maker` and `title` are required; `glaze` defaults to `"none"`.

Any other method or path answers 404 with `{"error": "not found"}`, and a body that is not a JSON object answers 400.

The queue lives in memory and starts with a few sample pieces, so every start of the server begins from the same queue.

## Tests

The tests start the server on a free port and use each endpoint over HTTP. Run them from the repository root with:

    python3 -m unittest discover -s tests -t .
