"""Menu items and the shop's menu catalogue."""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MenuItem:
    name: str
    base_price: float  # in dollars
    category: str      # "drink", "food", "extra"

    def __post_init__(self) -> None:
        if self.base_price < 0:
            raise ValueError(f"Price cannot be negative: {self.base_price}")


@dataclass
class Menu:
    items: Dict[str, MenuItem] = field(default_factory=dict)

    def add(self, item: MenuItem) -> None:
        self.items[item.name] = item

    def get(self, name: str) -> Optional[MenuItem]:
        return self.items.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.items


DEFAULT_MENU = Menu()
DEFAULT_MENU.add(MenuItem("Espresso",       2.50, "drink"))
DEFAULT_MENU.add(MenuItem("Latte",          4.50, "drink"))
DEFAULT_MENU.add(MenuItem("Cappuccino",     4.00, "drink"))
DEFAULT_MENU.add(MenuItem("Cold Brew",      5.00, "drink"))
DEFAULT_MENU.add(MenuItem("Croissant",      3.50, "food"))
DEFAULT_MENU.add(MenuItem("Blueberry Muffin", 3.00, "food"))
DEFAULT_MENU.add(MenuItem("Extra Shot",     0.75, "extra"))
DEFAULT_MENU.add(MenuItem("Oat Milk",       0.60, "extra"))
