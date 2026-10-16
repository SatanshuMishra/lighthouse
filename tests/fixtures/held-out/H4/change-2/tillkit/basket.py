from tillkit.pricing import line_total


def basket_summary(items):
    lines = [
        {"name": name, "quantity": quantity, "total_cents": line_total(unit_cents, quantity)}
        for name, unit_cents, quantity in items
    ]
    return {
        "lines": lines,
        "item_count": sum(line["quantity"] for line in lines),
        "total_cents": sum(line["total_cents"] for line in lines),
    }
