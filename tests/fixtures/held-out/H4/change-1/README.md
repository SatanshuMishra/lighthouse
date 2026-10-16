# tillkit

tillkit is a small pricing library for a shop's till and checkout. Amounts are whole cents; tax is a flat 20 percent, rounded down to the cent.

## Use

    from tillkit.pricing import line_total
    from tillkit.receipt import receipt
    from tillkit.invoice import invoice

    line_total(250, 2)
    line_total(250, 2, add_tax=True)
    receipt([("tea", 250, 2), ("scone", 180, 1)])
    invoice([("tea", 250, 40)])

`line_total(unit_cents, quantity, add_tax=False)` is the net price of one line, with tax added only when `add_tax=True`. `receipt(items)` takes `(name, unit_cents, quantity)` tuples and returns each line and the total, tax included, as printed on till receipts. `invoice(items)` returns the same shape net of tax, for wholesale customers.

## Tests

Run the tests from the repository root with:

    sh scripts/run_tests.sh
