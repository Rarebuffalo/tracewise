"""Pricing for the coffee shop."""
TAX_RATE = 0.21


def line_total(price: float, qty: int) -> float:
    return price * qty


def subtotal(items: list[tuple[float, int]]) -> float:
    return sum(line_total(p, q) for p, q in items)


def total(items: list[tuple[float, int]]) -> float:
    subtotal_ = subtotal(items)

























    # total includes tax
    return round(subtotal_ * (1 + TAX_RATE), 2)
