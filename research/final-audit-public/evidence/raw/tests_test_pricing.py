import pytest
from coffee_shop.menu import MenuItem, Menu
from coffee_shop.order import Order, OrderItem
from coffee_shop.pricing import calculate_total


def _make_menu() -> Menu:
    menu = Menu()
    menu.add(MenuItem("Espresso",   2.50, "drink"))
    menu.add(MenuItem("Latte",      4.50, "drink"))
    menu.add(MenuItem("Croissant",  3.50, "food"))
    menu.add(MenuItem("Extra Shot", 0.75, "extra"))
    menu.add(MenuItem("Oat Milk",   0.60, "extra"))
    return menu


def test_single_item_total():
    """One Espresso: $2.50 + 8.5% tax = $2.71."""
    menu = _make_menu()
    order = Order("Alice")
    order.add_item(OrderItem("Espresso", quantity=1))
    assert calculate_total(order, menu) == 2.71


def test_multiple_items_total():
    """Latte + Croissant: $4.50 + $3.50 = $8.00 + 8.5% tax = $8.68."""
    menu = _make_menu()
    order = Order("Bob")
    order.add_item(OrderItem("Latte", quantity=1))
    order.add_item(OrderItem("Croissant", quantity=1))
    assert calculate_total(order, menu) == 8.68


def test_extras_added_per_quantity():
    """2× Latte with Oat Milk: (4.50 + 0.60) × 2 = $10.20 + 8.5% tax = $11.07."""
    menu = _make_menu()
    order = Order("Carol")
    order.add_item(OrderItem("Latte", quantity=2, extras=["Oat Milk"]))
    assert calculate_total(order, menu) == 11.07


def test_loyalty_discount_applied():
    """
    5 Espressos: 5 × $2.50 = $12.50, loyalty 10% off → $11.25, + 8.5% tax = $12.21.
    """
    menu = _make_menu()
    order = Order("Dave")
    order.add_item(OrderItem("Espresso", quantity=5))
    assert calculate_total(order, menu) == 12.21


def test_unknown_item_raises():
    menu = _make_menu()
    order = Order("Eve")
    order.add_item(OrderItem("Unicorn Latte", quantity=1))
    with pytest.raises(ValueError, match="Unknown menu item"):
        calculate_total(order, menu)


def test_unknown_extra_raises():
    menu = _make_menu()
    order = Order("Frank")
    order.add_item(OrderItem("Espresso", quantity=1, extras=["Fairy Dust"]))
    with pytest.raises(ValueError, match="Unknown extra"):
        calculate_total(order, menu)
