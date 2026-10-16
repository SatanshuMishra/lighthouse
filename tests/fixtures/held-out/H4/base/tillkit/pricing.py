TAX_RATE_PERCENT = 20


def tax_on(net_cents):
    return net_cents * TAX_RATE_PERCENT // 100


def line_total(unit_cents, quantity, add_tax=True):
    net = unit_cents * quantity
    return net + tax_on(net) if add_tax else net
