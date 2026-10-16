# jotbook

jotbook is a tiny command-line notebook. It keeps numbered notes in one JSON file.

## Use

    python3 -m jotbook add --notebook notes.json "buy milk"
    python3 -m jotbook list --notebook notes.json

Every subcommand takes the shared `--notebook PATH` option naming the notes file. Without it, jotbook uses the file the `JOTBOOK_FILE` environment variable names, and otherwise `~/.jotbook.json`.

## Tests

Run the tests from the repository root with:

    python3 -m unittest discover -s tests
