# shelfapi

shelfapi is the HTTP JSON API behind a small lending library's catalogue and loans desk. It uses only the Python standard library.

## Use

Start the server, by default on port 8080:

    python3 -m shelfapi --port 8080

Endpoints, each answering GET with a JSON object:

- `/books`: `{"books": [{"id", "title", "author", "added"}]}`, where `added` is the day the book joined the catalogue.
- `/loans`: `{"loans": [{"id", "book", "member", "due"}]}`, where `due` is the day the book must come back.

Every day in a response is an ISO 8601 date such as `2024-03-05`. The loans desk and the members' app both read these fields.

Any other path answers 404 with `{"error": "not found"}`.

## Tests

The tests start the server on a free port and check each endpoint's status code and keys. Run them from the repository root with:

    python3 -m unittest discover -s tests
