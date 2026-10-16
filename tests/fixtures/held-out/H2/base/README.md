# Steepwell

A single web page that times a cup of tea. Pick the tea, press Start, and the clock counts down to Ready; press Stop to cancel. It is plain HTML, CSS and JavaScript with no build step.

## Use

Start the page's own server from the repository root:

    python3 serve.py

then open http://127.0.0.1:8000/ in a browser. Pass `--port N` to use another port, or `--port 0` for any free one; the server prints the address it listens on.

## Tests

The tests start the server on a free port and check that it serves every file under public/. Run them from the repository root with:

    python3 -m unittest discover -s tests -t .
