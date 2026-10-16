# quillmark

quillmark fills message templates with named fields, for mail merges, reminders and receipts sent by a calling program.

## Use

    from quillmark.parser import fields
    from quillmark.render import render

    fields("Dear {name}, your order ships {weekday}.")
    render("Dear {name}, your order ships {weekday}.", {"name": "Ada", "weekday": "Monday"})

A field is a name in braces. `fields(template)` lists a template's field names in order. `render(template, values)` returns the template with each field replaced by its value from the `values` mapping, and raises `MissingField` when a field has no value.

## Tests

Run the tests from the repository root with:

    sh scripts/check.sh
