# quillmark

quillmark fills message templates with named fields, for mail merges, reminders and receipts sent by a calling program.

## Use

    from quillmark.parser import fields
    from quillmark.render import render

    fields("Dear {name|friend}, your order ships {weekday}.")
    render("Dear {name|friend}, your order ships {weekday}.", {"name": "Ada", "weekday": "Monday"})
    render("Dear {name|friend}, your order ships {weekday}.", {"weekday": "Tuesday"})

A field is a name in braces, optionally followed by `|` and a default. `fields(template)` lists a template's fields in order, as written. `render(template, values)` returns the template with each field replaced by its value from the `values` mapping. A field with no value renders its default, and `render` raises `MissingField` when a field has neither a value nor a default.

## Tests

Run the tests from the repository root with:

    sh scripts/check.sh
