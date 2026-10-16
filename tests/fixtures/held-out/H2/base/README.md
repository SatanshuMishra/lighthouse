# Pantry list

A single web page for jotting down what the pantry needs. Type an item and press Add, or Enter, and it joins the list; the count under the list keeps track. It is plain HTML and JavaScript with no build step.

## Use

Serve the page and open it in a browser:

    python3 -m http.server 8000 --directory site

then visit http://localhost:8000/.

## Tests

The tests start a local server and check every file under site/ is served. Run them from the repository root with:

    python3 -m unittest discover -s tests
