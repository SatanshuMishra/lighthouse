# tillkit

tillkit is a small pricing library for a shop's till and checkout. Amounts are whole cents; tax is a flat 20 percent, rounded down to the cent.

## Use

    from tillkit.pricing import line_total
    from tillkit.receipt import receipt

    line_total(250, 2)
    line_total(250, 2, add_tax=False)
    receipt([("tea", 250, 2), ("scone", 180, 1)])

`line_total(unit_cents, quantity, add_tax=True)` is the price of one line, tax included unless `add_tax=False`. `receipt(items)` takes `(name, unit_cents, quantity)` tuples and returns each line and the total, tax included, as printed on till receipts.

## Tests

Run the tests from the repository root with:

    sh scripts/run_tests.sh
