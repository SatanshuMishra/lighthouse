# milepost

milepost is a small command-line log of car journeys for mileage claims. It keeps every trip in one JSON file.

## Use

    python3 -m milepost log 2026-03-02 Lyon 42
    python3 -m milepost show
    python3 -m milepost total
    python3 -m milepost drop 2

`log DATE PLACE KM` records one trip. `show` prints every trip with its number. `total` adds up the distance of every trip. `drop N` removes the trip `show` numbers N, for when a trip was logged by mistake.

Trips live in `milepost.json` in the current folder, or in the file the `MILEPOST_DATA` environment variable names.

## Tests

Run the tests from the repository root with:

    python3 -m unittest discover -s tests
