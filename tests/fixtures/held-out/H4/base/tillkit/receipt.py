from tillkit.pricing import line_total


def receipt(items):
    lines = [
        {"name": name, "quantity": quantity, "total_cents": line_total(unit_cents, quantity)}
        for name, unit_cents, quantity in items
    ]
    return {"lines": lines, "total_cents": sum(line["total_cents"] for line in lines)}
