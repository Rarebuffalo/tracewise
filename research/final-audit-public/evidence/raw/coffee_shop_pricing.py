"""
Pricing logic — calculates the total cost of an order.

Rules:
- Each item is charged at base_price × quantity
- Extras are looked up on the menu and added per unit of the parent item
- A loyalty discount of 10% is applied when the order has 5 or more items
- Tax rate is 8.5%
"""

from .menu import Menu, DEFAULT_MENU
from .order import Order

TAX_RATE = 0.085
LOYALTY_THRESHOLD = 5
LOYALTY_DISCOUNT = 0.10


def calculate_total(order: Order, menu: Menu = DEFAULT_MENU) -> float:
    """Return the total price including extras, loyalty discount, and tax."""
    subtotal = 0.0

    for order_item in order.items:
        item = menu.get(order_item.menu_item_name)
        if item is None:
            raise ValueError(f"Unknown menu item: {order_item.menu_item_name!r}")

        line = item.base_price * order_item.quantity

        for extra_name in order_item.extras:
            extra = menu.get(extra_name)
            if extra is None:
                raise ValueError(f"Unknown extra: {extra_name!r}")
            line += extra.base_price * order_item.quantity

        subtotal += line

    if order.item_count() >= LOYALTY_THRESHOLD:
        subtotal *= (1 - LOYALTY_DISCOUNT)

    total = subtotal * TAX_RATE

    return round(total, 2)
